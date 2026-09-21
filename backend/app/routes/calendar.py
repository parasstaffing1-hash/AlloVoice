"""Google Calendar integration for VoiceField (graceful, mock-testable).

No live keys required:
- GET /google/auth builds a real OAuth URL keylessly (never calls Google).
- GET /google/callback exchanges ?code= via httpx; failures -> 502.
- POST /sync?provider=google pushes upcoming scheduled jobs (next 30d,
  limit 50) as Google Calendar events; unusable config -> 503.
- Per-user tokens live in module dict ``_GOOGLE_TOKENS`` keyed by user id
  str -> {access_token, refresh_token, expires_at, last_synced}.
  CalendarSync rows are updated best-effort where present (never fatal).
  NOTE: module dict does not survive restarts; CalendarSync table is the
  durable fallback.
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

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/calendar"
)

NOT_CONNECTED_DETAIL = "Google Calendar not connected — add GOOGLE_* keys and connect"
NOT_AUTHORISED_DETAIL = "Google Calendar not connected — complete OAuth connect first"

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
_GOOGLE_TOKENS: dict[str, dict[str, Any]] = {}

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


def _google_usable() -> bool:
    try:
        settings = get_settings()
        cid = str(getattr(settings, "GOOGLE_CLIENT_ID", "") or "")
        secret = str(getattr(settings, "GOOGLE_CLIENT_SECRET", "") or "")
    except Exception:
        return False
    if not cid.strip() or not secret.strip():
        return False
    if _looks_placeholder(cid) or _looks_placeholder(secret):
        return False
    return True


def _require_google_usable() -> None:
    if not _google_usable():
        raise HTTPException(status_code=503, detail=NOT_CONNECTED_DETAIL)


def _google_redirect_uri() -> str:
    try:
        settings = get_settings()
        configured = str(getattr(settings, "GOOGLE_REDIRECT_URI", "") or "").strip()
        if configured:
            return configured
        app_url = str(getattr(settings, "APP_URL", "") or "http://localhost:3002").rstrip("/")
    except Exception:
        app_url = "http://localhost:3002"
    return f"{app_url}/api/calendar/google/callback"


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


async def _get_google_token(user_id: str) -> str:
    """Return a valid Google access token, refreshing when expiring."""
    entry = _GOOGLE_TOKENS.get(str(user_id))
    if not entry or not entry.get("refresh_token"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)
    expires_at = _as_aware(entry.get("expires_at"))
    now = _utcnow()
    if entry.get("access_token") and expires_at is not None and expires_at > now + timedelta(seconds=60):
        return str(entry["access_token"])

    settings = get_settings()
    client_id = str(getattr(settings, "GOOGLE_CLIENT_ID", "") or "")
    client_secret = str(getattr(settings, "GOOGLE_CLIENT_SECRET", "") or "")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": entry["refresh_token"],
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Google token refresh failed")
    except Exception:
        raise HTTPException(status_code=502, detail="Google token refresh failed")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Google token refresh failed")
    try:
        data = resp.json()
        access_token = data["access_token"]
        refresh_token = data.get("refresh_token") or entry["refresh_token"]
        expires_in = int(data.get("expires_in", 3600))
    except Exception:
        raise HTTPException(status_code=502, detail="Google token refresh failed")
    entry["access_token"] = access_token
    entry["refresh_token"] = refresh_token
    entry["expires_at"] = now + timedelta(seconds=expires_in)
    _GOOGLE_TOKENS[str(user_id)] = entry
    return str(access_token)


def _build_google_event(job: Job, customer_name: str = "", location: str = "") -> dict[str, Any]:
    start = getattr(job, "scheduled_at", None)
    if isinstance(start, datetime):
        aware_start = start if start.tzinfo is not None else start.replace(tzinfo=timezone.utc)
    else:
        aware_start = _utcnow()
    end = aware_start + timedelta(hours=1)
    description_parts: list[str] = []
    if getattr(job, "description", None):
        description_parts.append(str(job.description))
    if customer_name:
        description_parts.append(f"Customer: {customer_name}")
    description_parts.append(f"Job: {getattr(job, 'title', '')} ({getattr(job, 'id', '')})")
    return {
        "summary": getattr(job, "title", None) or "Allo Job",
        "description": "\n".join(description_parts),
        "location": location or "",
        "start": {"dateTime": aware_start.isoformat(), "timeZone": "Europe/London"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Europe/London"},
    }


async def _upsert_calendar_sync(
    db: AsyncSession, user: User, access_token: str, refresh_token: str, expires_at: datetime
) -> None:
    """Best-effort durable persist of tokens to CalendarSync (never raises)."""
    try:
        result = await db.execute(
            select(CalendarSync).where(
                CalendarSync.user_id == user.id, CalendarSync.provider == "google"
            )
        )
        row = result.scalar_one_or_none()
        naive_expires = expires_at.replace(tzinfo=None) if expires_at.tzinfo else expires_at
        if row is None:
            row = CalendarSync(
                user_id=user.id,
                provider="google",
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


def _google_connected(user_id: str) -> bool:
    entry = _GOOGLE_TOKENS.get(str(user_id))
    return bool(entry and entry.get("access_token"))


# ─── OAuth ────────────────────────────────────────────────────────────

def _build_google_auth_url() -> str:
    try:
        settings = get_settings()
        client_id = str(getattr(settings, "GOOGLE_CLIENT_ID", "") or "")
    except Exception:
        client_id = ""
    params = {
        "client_id": client_id,
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


@router.get("/google/auth")
async def google_auth() -> dict[str, str]:
    """Return the Google OAuth consent URL (works keyless; never calls Google)."""
    return {"auth_url": _build_google_auth_url()}


# Legacy alias: original route was POST /google/auth.
@router.post("/google/auth", include_in_schema=False)
async def google_auth_legacy() -> dict[str, str]:
    return {"auth_url": _build_google_auth_url()}


@router.get("/google/callback")
async def google_callback(
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

    _require_google_usable()

    settings = get_settings()
    client_id = str(getattr(settings, "GOOGLE_CLIENT_ID", "") or "")
    client_secret = str(getattr(settings, "GOOGLE_CLIENT_SECRET", "") or "")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _google_redirect_uri(),
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Google token exchange failed")
    except Exception:
        raise HTTPException(status_code=502, detail="Google token exchange failed")

    if token_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Google token exchange failed")
    try:
        tokens = token_response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")
        expires_in = int(tokens.get("expires_in", 3600))
    except Exception:
        raise HTTPException(status_code=502, detail="Google token exchange failed")

    if not refresh_token:
        # offline access should yield a refresh token; keep entry usable anyway
        existing = _GOOGLE_TOKENS.get(str(current_user.id), {})
        refresh_token = str(existing.get("refresh_token", "") or "")

    expires_at = _utcnow() + timedelta(seconds=expires_in)
    _GOOGLE_TOKENS[str(current_user.id)] = {
        "access_token": str(access_token),
        "refresh_token": str(refresh_token),
        "expires_at": expires_at,
        "last_synced": _GOOGLE_TOKENS.get(str(current_user.id), {}).get("last_synced"),
    }
    await _upsert_calendar_sync(db, current_user, str(access_token), str(refresh_token), expires_at)
    return {"connected": True}


# ─── Sync ─────────────────────────────────────────────────────────────

@router.post("/sync")
async def sync_calendar(
    provider: str = "google",
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> dict[str, Any]:
    """Push upcoming scheduled jobs to Google Calendar (provider=google)."""
    if (provider or "").lower() != "google":
        raise HTTPException(status_code=400, detail="Unsupported provider (use google)")
    # Usability gate first so keyless callers always see 503 (even unauthenticated).
    _require_google_usable()
    current_user = await _require_user(credentials, db)

    try:
        result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
        business = result.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    user_key = str(current_user.id)
    entry = _GOOGLE_TOKENS.get(user_key)
    if not entry or not entry.get("access_token"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)

    access_token = await _get_google_token(user_key)

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
        raise HTTPException(status_code=502, detail="Google sync failed")

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
                payload = _build_google_event(job, customer_name, location)
                resp = await http_client.post(
                    GOOGLE_EVENTS_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except httpx.HTTPError:
                errors.append({"job": str(job.id), "error": "Google request failed"})
                continue
            except Exception:
                errors.append({"job": str(job.id), "error": "Google request failed"})
                continue
            if resp.status_code in (200, 201):
                try:
                    body = resp.json()
                    event_id = body.get("id")
                    if event_id:
                        job.google_calendar_event_id = str(event_id)
                    synced += 1
                except Exception:
                    errors.append({"job": str(job.id), "error": "Local mark-synced failed"})
            else:
                errors.append({"job": str(job.id), "error": f"Google rejected event ({resp.status_code})"})

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
                CalendarSync.user_id == current_user.id, CalendarSync.provider == "google"
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
async def calendar_status(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> dict[str, Any]:
    """Connection state for google (+outlook mirror); never calls Google."""
    try:
        current_user = await _resolve_user(credentials, db)
        if current_user is None:
            return {"google": False, "outlook": False, "connected": False, "last_synced": None}
        google_on = _google_connected(str(current_user.id))
        last_synced: Any = _GOOGLE_TOKENS.get(str(current_user.id), {}).get("last_synced")
        outlook_on = False
        try:
            result = await db.execute(
                select(CalendarSync).where(CalendarSync.user_id == current_user.id)
            )
            syncs = list(result.scalars().all())
            for s in syncs:
                if s.provider == "google" and s.sync_enabled and s.access_token:
                    google_on = True
                    if s.last_synced_at and last_synced is None:
                        last_synced = s.last_synced_at.isoformat() if isinstance(s.last_synced_at, datetime) else s.last_synced_at
                if s.provider in ("outlook", "microsoft") and s.sync_enabled and s.access_token:
                    outlook_on = True
        except Exception:
            pass
        # Mirror live outlook module dict when available (same process).
        try:
            from app.routes import outlook as _outlook_mod  # type: ignore

            entry = _outlook_mod._OUTLOOK_TOKENS.get(str(current_user.id))
            if entry and entry.get("access_token"):
                outlook_on = True
        except Exception:
            pass
        return {
            "google": google_on,
            "outlook": outlook_on,
            "connected": google_on,
            "last_synced": last_synced,
        }
    except HTTPException:
        raise
    except Exception:
        return {"google": False, "outlook": False, "connected": False, "last_synced": None}


async def _do_disconnect(provider: str, current_user: User, db: AsyncSession) -> dict[str, Any]:
    provider = (provider or "google").lower()
    if provider not in ("google",):
        raise HTTPException(status_code=400, detail="Unsupported provider (use google)")
    _GOOGLE_TOKENS.pop(str(current_user.id), None)
    try:
        result = await db.execute(
            select(CalendarSync).where(
                CalendarSync.user_id == current_user.id, CalendarSync.provider == "google"
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


@router.post("/disconnect")
async def calendar_disconnect(
    provider: str = "google",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Clear the caller's Google tokens (provider=google)."""
    return await _do_disconnect(provider, current_user, db)


@router.post("/google/disconnect", include_in_schema=False)
async def google_disconnect_alias(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _do_disconnect("google", current_user, db)
