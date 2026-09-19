"""Microsoft (Outlook) calendar integration for VoiceField (graceful, mock-testable).

Raw httpx OAuth against login.microsoftonline.com (no msal dependency at
runtime, fewer moving parts):

- GET /auth builds a real authorize URL keylessly (never calls Microsoft).
- GET /callback?code= exchanges via httpx; failures -> 502.
- POST /sync pushes upcoming scheduled jobs (next 30d, limit 50) as Graph
  /me/calendar/events; unusable config -> 503.
- Per-user tokens live in module dict ``_OUTLOOK_TOKENS`` keyed by user id
  str -> {access_token, refresh_token, expires_at, last_synced}.
  CalendarSync rows (provider="outlook") are updated best-effort.
  NOTE: module dict does not survive restarts; CalendarSync is the durable
  fallback.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Business, CalendarSync, Customer, Job, JobStatus, Property, User
from app.routes.auth import get_current_user
from app.services.auth import decode_access_token

router = APIRouter(prefix="/api/outlook", tags=["outlook"])

GRAPH_EVENTS_URL = "https://graph.microsoft.com/v1.0/me/calendar/events"

MS_SCOPES = "https://graph.microsoft.com/Calendars.ReadWrite offline_access"

NOT_CONNECTED_DETAIL = "Outlook not connected — add MS_* keys and connect"
NOT_AUTHORISED_DETAIL = "Outlook not connected — complete OAuth connect first"

_PLACEHOLDER_MARKERS = (
    "placeholder",
    "changeme",
    "change-me",
    "change_me",
    "example",
    "dummy",
    "your-",
    "your_",
    "test-key",
    "test_key",
    "xxx",
)
_PLACEHOLDER_EXACT = {"", "none", "null", "test", "testing", "changeme", "placeholder"}

# user_id str -> {access_token, refresh_token, expires_at, last_synced}
_OUTLOOK_TOKENS: dict[str, dict[str, Any]] = {}

_optional_bearer = HTTPBearer(auto_error=False)


# ─── Helpers ──────────────────────────────────────────────────────────

def _looks_placeholder(value: Any) -> bool:
    s = str(value or "").strip()
    if not s:
        return True
    low = s.lower()
    if low in _PLACEHOLDER_EXACT:
        return True
    return any(marker in low for marker in _PLACEHOLDER_MARKERS)


def _ms_usable() -> bool:
    try:
        settings = get_settings()
        cid = str(getattr(settings, "MS_CLIENT_ID", "") or "")
        secret = str(getattr(settings, "MS_CLIENT_SECRET", "") or "")
    except Exception:
        return False
    if not cid.strip() or not secret.strip():
        return False
    if _looks_placeholder(cid) or _looks_placeholder(secret):
        return False
    return True


def _require_ms_usable() -> None:
    if not _ms_usable():
        raise HTTPException(status_code=503, detail=NOT_CONNECTED_DETAIL)


def _tenant() -> str:
    try:
        settings = get_settings()
        tenant = str(getattr(settings, "MS_TENANT_ID", "") or "").strip()
        if tenant:
            return tenant
    except Exception:
        pass
    return "common"


def _ms_redirect_uri() -> str:
    try:
        settings = get_settings()
        configured = str(getattr(settings, "MS_REDIRECT_URI", "") or "").strip()
        if configured:
            return configured
        app_url = str(getattr(settings, "APP_URL", "") or "http://localhost:3002").rstrip("/")
    except Exception:
        app_url = "http://localhost:3002"
    return f"{app_url}/api/outlook/callback"


def _authorize_url() -> str:
    return f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/authorize"


def _token_url() -> str:
    return f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/token"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _resolve_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: AsyncSession,
) -> Optional[User]:
    try:
        if credentials is None:
            return None
        payload = decode_access_token(credentials.credentials)
        if not payload:
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            return None
        return user
    except Exception:
        return None


async def _require_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: AsyncSession,
) -> User:
    user = await _resolve_user(credentials, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def _get_ms_token(user_id: str) -> str:
    entry = _OUTLOOK_TOKENS.get(str(user_id))
    if not entry or not entry.get("refresh_token"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)
    expires_at = _as_aware(entry.get("expires_at"))
    now = _utcnow()
    if entry.get("access_token") and expires_at is not None and expires_at > now + timedelta(seconds=60):
        return str(entry["access_token"])

    settings = get_settings()
    client_id = str(getattr(settings, "MS_CLIENT_ID", "") or "")
    client_secret = str(getattr(settings, "MS_CLIENT_SECRET", "") or "")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _token_url(),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": entry["refresh_token"],
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": MS_SCOPES,
                },
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Microsoft token refresh failed")
    except Exception:
        raise HTTPException(status_code=502, detail="Microsoft token refresh failed")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Microsoft token refresh failed")
    try:
        data = resp.json()
        access_token = data["access_token"]
        refresh_token = data.get("refresh_token") or entry["refresh_token"]
        expires_in = int(data.get("expires_in", 3600))
    except Exception:
        raise HTTPException(status_code=502, detail="Microsoft token refresh failed")
    entry["access_token"] = access_token
    entry["refresh_token"] = refresh_token
    entry["expires_at"] = now + timedelta(seconds=expires_in)
    _OUTLOOK_TOKENS[str(user_id)] = entry
    return str(access_token)


def _build_graph_event(job: Job, customer_name: str = "", location: str = "") -> dict[str, Any]:
    start = getattr(job, "scheduled_at", None)
    if isinstance(start, datetime):
        aware_start = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
    else:
        aware_start = _utcnow()
    end = aware_start + timedelta(hours=1)
    body_parts: list[str] = []
    if getattr(job, "description", None):
        body_parts.append(str(job.description))
    if customer_name:
        body_parts.append(f"Customer: {customer_name}")
    body_parts.append(f"Job: {getattr(job, 'title', '')} ({getattr(job, 'id', '')})")
    return {
        "subject": getattr(job, "title", None) or "VoiceField Job",
        "body": {"contentType": "text", "content": "\n".join(body_parts)},
        "location": {"displayName": location or ""},
        "start": {"dateTime": aware_start.isoformat(), "timeZone": "Europe/London"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Europe/London"},
    }


async def _upsert_calendar_sync(
    db: AsyncSession, user: User, access_token: str, refresh_token: str, expires_at: datetime
) -> None:
    try:
        result = await db.execute(
            select(CalendarSync).where(
                CalendarSync.user_id == user.id, CalendarSync.provider == "outlook"
            )
        )
        row = result.scalar_one_or_none()
        naive_expires = expires_at.replace(tzinfo=None) if expires_at.tzinfo else expires_at
        if row is None:
            row = CalendarSync(
                user_id=user.id,
                provider="outlook",
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires=naive_expires,
                sync_enabled=True,
            )
            db.add(row)
        else:
            row.access_token = access_token
            row.refresh_token = refresh_token
            row.token_expires = naive_expires
            row.sync_enabled = True
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass


def _build_auth_url() -> str:
    try:
        settings = get_settings()
        client_id = str(getattr(settings, "MS_CLIENT_ID", "") or "")
    except Exception:
        client_id = ""
    params = {
        "client_id": client_id,
        "redirect_uri": _ms_redirect_uri(),
        "response_type": "code",
        "response_mode": "query",
        "scope": MS_SCOPES,
    }
    return f"{_authorize_url()}?{urlencode(params)}"


# ─── OAuth ────────────────────────────────────────────────────────────

@router.get("/auth")
async def outlook_auth() -> dict[str, str]:
    """Return the Microsoft OAuth consent URL (works keyless; never calls Microsoft)."""
    return {"auth_url": _build_auth_url()}


@router.get("/callback")
async def outlook_callback(
    code: str,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> dict[str, bool]:
    """Exchange an OAuth code for tokens and store them per-user."""
    current_user = await _resolve_user(credentials, db)
    if current_user is None and state:
        try:
            from uuid import UUID as _UUID

            user_id = _UUID(str(state))
            result = await db.execute(select(User).where(User.id == user_id))
            state_user = result.scalar_one_or_none()
            if state_user is not None:
                current_user = state_user
        except Exception:
            current_user = None
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    _require_ms_usable()

    settings = get_settings()
    client_id = str(getattr(settings, "MS_CLIENT_ID", "") or "")
    client_secret = str(getattr(settings, "MS_CLIENT_SECRET", "") or "")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                _token_url(),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _ms_redirect_uri(),
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": MS_SCOPES,
                },
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Microsoft token exchange failed")
    except Exception:
        raise HTTPException(status_code=502, detail="Microsoft token exchange failed")

    if token_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Microsoft token exchange failed")
    try:
        tokens = token_response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")
        expires_in = int(tokens.get("expires_in", 3600))
    except Exception:
        raise HTTPException(status_code=502, detail="Microsoft token exchange failed")

    if not refresh_token:
        existing = _OUTLOOK_TOKENS.get(str(current_user.id), {})
        refresh_token = str(existing.get("refresh_token", "") or "")

    expires_at = _utcnow() + timedelta(seconds=expires_in)
    _OUTLOOK_TOKENS[str(current_user.id)] = {
        "access_token": str(access_token),
        "refresh_token": str(refresh_token),
        "expires_at": expires_at,
        "last_synced": _OUTLOOK_TOKENS.get(str(current_user.id), {}).get("last_synced"),
    }
    await _upsert_calendar_sync(db, current_user, str(access_token), str(refresh_token), expires_at)
    return {"connected": True}


# ─── Sync ─────────────────────────────────────────────────────────────

@router.post("/sync")
async def sync_outlook(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> dict[str, Any]:
    """Push upcoming scheduled jobs to the Microsoft calendar."""
    # Usability gate first so keyless callers always see 503 (even unauthenticated).
    _require_ms_usable()
    current_user = await _require_user(credentials, db)

    try:
        result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
        business = result.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    user_key = str(current_user.id)
    entry = _OUTLOOK_TOKENS.get(user_key)
    if not entry or not entry.get("access_token"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)

    access_token = await _get_ms_token(user_key)

    now = datetime.utcnow()
    window_end = now + timedelta(days=30)
    try:
        jobs_result = await db.execute(
            select(Job)
            .where(
                Job.business_id == business.id,
                Job.status == JobStatus.SCHEDULED,
                Job.scheduled_at.isnot(None),
                Job.scheduled_at >= now,
                Job.scheduled_at <= window_end,
            )
            .order_by(Job.scheduled_at)
            .limit(50)
        )
        jobs = list(jobs_result.scalars().all())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")

    synced = 0
    errors: list[dict[str, str]] = []

    try:
        http_client = httpx.AsyncClient(timeout=20)
    except Exception:
        raise HTTPException(status_code=502, detail="Outlook sync failed")

    async with http_client:
        for job in jobs:
            customer_name = ""
            location = ""
            try:
                cust_result = await db.execute(select(Customer).where(Customer.id == job.customer_id))
                customer = cust_result.scalar_one_or_none()
                if customer is not None:
                    customer_name = (customer.full_name or "").strip()
            except Exception:
                customer = None
            try:
                if getattr(job, "property_id", None):
                    prop_result = await db.execute(
                        select(Property).where(Property.id == job.property_id)
                    )
                    prop = prop_result.scalar_one_or_none()
                    if prop is not None:
                        location = " ".join(
                            p for p in [prop.address_line1 or "", prop.city or "", prop.zip_code or ""] if p
                        )
            except Exception:
                pass
            try:
                payload = _build_graph_event(job, customer_name, location)
                resp = await http_client.post(
                    GRAPH_EVENTS_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except httpx.HTTPError:
                errors.append({"job": str(job.id), "error": "Microsoft request failed"})
                continue
            except Exception:
                errors.append({"job": str(job.id), "error": "Microsoft request failed"})
                continue
            if resp.status_code in (200, 201):
                try:
                    body = resp.json()
                    event_id = body.get("id")
                    if event_id:
                        job.outlook_calendar_event_id = str(event_id)
                    synced += 1
                except Exception:
                    errors.append({"job": str(job.id), "error": "Local mark-synced failed"})
            else:
                errors.append({"job": str(job.id), "error": f"Microsoft rejected event ({resp.status_code})"})

    try:
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="Database unavailable")

    iso_now = _utcnow().isoformat()
    entry["last_synced"] = iso_now
    try:
        sync_result = await db.execute(
            select(CalendarSync).where(
                CalendarSync.user_id == current_user.id, CalendarSync.provider == "outlook"
            )
        )
        row = sync_result.scalar_one_or_none()
        if row is not None:
            row.last_synced_at = datetime.utcnow()
            await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    return {"synced": synced, "errors": errors}


# ─── Status / disconnect ──────────────────────────────────────────────

@router.get("/status")
async def outlook_status(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> dict[str, Any]:
    """Connection state; never calls Microsoft."""
    try:
        current_user = await _resolve_user(credentials, db)
        if current_user is None:
            return {"connected": False, "outlook": False, "google": False, "last_synced": None}
        entry = _OUTLOOK_TOKENS.get(str(current_user.id))
        connected = bool(entry and entry.get("access_token"))
        last_synced: Any = (entry or {}).get("last_synced")
        try:
            result = await db.execute(
                select(CalendarSync).where(
                    CalendarSync.user_id == current_user.id, CalendarSync.provider == "outlook"
                )
            )
            row = result.scalar_one_or_none()
            if row is not None and row.sync_enabled and row.access_token:
                connected = True
                if last_synced is None and row.last_synced_at:
                    last_synced = row.last_synced_at.isoformat() if isinstance(row.last_synced_at, datetime) else row.last_synced_at
        except Exception:
            pass
        return {
            "connected": connected,
            "outlook": connected,
            "google": False,
            "last_synced": last_synced,
        }
    except HTTPException:
        raise
    except Exception:
        return {"connected": False, "outlook": False, "google": False, "last_synced": None}


@router.post("/disconnect")
async def outlook_disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Clear the caller's Microsoft tokens."""
    _OUTLOOK_TOKENS.pop(str(current_user.id), None)
    try:
        result = await db.execute(
            select(CalendarSync).where(
                CalendarSync.user_id == current_user.id, CalendarSync.provider == "outlook"
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            row.sync_enabled = False
            row.access_token = None
            row.refresh_token = None
            await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
    return {"connected": False, "disconnected": True}
