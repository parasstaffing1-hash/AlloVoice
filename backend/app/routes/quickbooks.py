"""QuickBooks Online integration for VoiceField (UK field service SaaS, GBP focus).

Hardened, mock-testable design (no live keys required):

- Degrades gracefully when QB_CLIENT_ID / QB_CLIENT_SECRET are missing,
  empty, or obvious placeholders: live sync endpoints return HTTP 503 with a
  clean message instead of calling Intuit. Tracebacks are never leaked.
- OAuth2 authorization URL builder (works keyless — URL building only) +
  code exchange against Intuit token service with HTTP Basic auth
  (client_id:client_secret). All network failures surface as HTTP 502.
- Per-business OAuth token store kept in module-level ``_qb_tokens`` dict
  keyed by business id (str): {access_token, refresh_token, realm_id,
  expires_at, company_name, last_synced}. Global ``_quickbooks_state``
  fallback retained for single-tenant dev compat.
- Sync endpoints push REAL entities to the QBO v3 Accounting API
  (https://sandbox-quickbooks.api.intuit.com or
  https://quickbooks.api.intuit.com, minorversion=75, Bearer + Accept json):
  invoices as Invoice with CustomerRef + Line items (query existing Customer
  by DisplayName first, create if missing); contacts as Customer; payments
  as Payment. Tenancy via Business lookup (owner_id == current_user.id).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Business, Customer, Invoice, InvoiceItem, Payment, PaymentStatus, User
from app.routes.auth import get_current_user
from app.services.auth import decode_access_token

router = APIRouter(prefix="/api/quickbooks", tags=["quickbooks"])

QB_AUTH_BASE_URL = "https://appcenter.intuit.com/connect/oauth2"
QB_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QB_SANDBOX_API_BASE = "https://sandbox-quickbooks.api.intuit.com"
QB_PROD_API_BASE = "https://quickbooks.api.intuit.com"
QB_MINOR_VERSION = "75"
QB_SCOPES = "com.intuit.quickbooks.accounting openid profile email"

NOT_CONNECTED_DETAIL = "QuickBooks not connected — add QB_* keys and connect"
NOT_AUTHORISED_DETAIL = "QuickBooks not connected — complete OAuth connect first"

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
_PLACEHOLDER_EXACT = {
    "",
    "none",
    "null",
    "test",
    "testing",
    "changeme",
    "placeholder",
}

# Module-level connection state (global fallback for single-tenant dev).
_quickbooks_state: dict = {
    "connected": False,
    "company_name": None,
    "last_synced": None,
}

# OAuth tokens keyed by business id (str) -> token dict.
# {access_token, refresh_token, realm_id, expires_at, company_name, last_synced, connected_at}
_qb_tokens: dict[str, dict] = {}

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


def _qb_settings() -> tuple[str, str, str, str]:
    """Return (client_id, client_secret, redirect_uri, environment)."""
    try:
        settings = get_settings()
        client_id = str(getattr(settings, "QB_CLIENT_ID", "") or "")
        client_secret = str(getattr(settings, "QB_CLIENT_SECRET", "") or "")
        redirect_cfg = str(getattr(settings, "QB_REDIRECT_URI", "") or "").strip()
        env = str(getattr(settings, "QB_ENVIRONMENT", "") or "sandbox").strip().lower() or "sandbox"
        app_url = str(getattr(settings, "APP_URL", "") or "http://localhost:3002").rstrip("/")
    except Exception:
        client_id = os.getenv("QB_CLIENT_ID", "")
        client_secret = os.getenv("QB_CLIENT_SECRET", "")
        redirect_cfg = os.getenv("QB_REDIRECT_URI", "").strip()
        env = (os.getenv("QB_ENVIRONMENT", "sandbox") or "sandbox").strip().lower()
        app_url = (os.getenv("APP_URL", "http://localhost:3002") or "http://localhost:3002").rstrip("/")
    if redirect_cfg:
        redirect_uri = redirect_cfg
    else:
        redirect_uri = f"{app_url}/settings?tab=integrations&provider=quickbooks"
    if not client_id:
        client_id = os.getenv("QB_CLIENT_ID", "") or ""
    if not client_secret:
        client_secret = os.getenv("QB_CLIENT_SECRET", "") or ""
    return client_id, client_secret, redirect_uri, env


def _qb_usable() -> bool:
    """True only when a real (non-empty, non-placeholder) id+secret are set."""
    try:
        client_id, client_secret, _, _ = _qb_settings()
    except Exception:
        return False
    if not (client_id or "").strip() or not (client_secret or "").strip():
        return False
    if _looks_placeholder(client_id) or _looks_placeholder(client_secret):
        return False
    return True


def _require_usable() -> None:
    if not _qb_usable():
        raise HTTPException(status_code=503, detail=NOT_CONNECTED_DETAIL)


def _qb_api_base() -> str:
    try:
        _, _, _, env = _qb_settings()
    except Exception:
        env = "sandbox"
    if env == "production":
        return QB_PROD_API_BASE
    return QB_SANDBOX_API_BASE


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


async def _get_business(current_user: User, db: AsyncSession) -> Optional[Business]:
    try:
        result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
        return result.scalar_one_or_none()
    except Exception:
        return None


async def _get_business_id(current_user: User, db: AsyncSession):
    """Best-effort business lookup; returns None instead of raising."""
    try:
        result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
        business = result.scalar_one_or_none()
        return business.id if business else None
    except Exception:
        return None


async def _refresh_token_if_needed(business_id: str) -> str:
    """Return a valid access token, refreshing via Intuit when expiring. 502 on failure."""
    entry = _qb_tokens.get(str(business_id))
    if not entry or not entry.get("refresh_token"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)
    expires_at = _as_aware(entry.get("expires_at"))
    now = datetime.now(timezone.utc)
    if entry.get("access_token") and expires_at is not None and expires_at > now + timedelta(seconds=60):
        return str(entry["access_token"])
    client_id, client_secret, redirect_uri, _ = _qb_settings()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                QB_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": entry["refresh_token"],
                },
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="QuickBooks token refresh failed")
    except Exception:
        raise HTTPException(status_code=502, detail="QuickBooks token refresh failed")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="QuickBooks token refresh failed")
    try:
        data = resp.json()
        access_token = data["access_token"]
        refresh_token = data.get("refresh_token") or entry["refresh_token"]
        expires_in = int(data.get("expires_in", 3600))
    except Exception:
        raise HTTPException(status_code=502, detail="QuickBooks token refresh failed")
    entry["access_token"] = access_token
    entry["refresh_token"] = refresh_token
    entry["expires_at"] = now + timedelta(seconds=expires_in)
    _qb_tokens[str(business_id)] = entry
    return str(access_token)


def _qb_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def _qb_ensure_customer(
    client: httpx.AsyncClient, api_base: str, realm_id: str, headers: dict, customer: Customer
) -> tuple[Optional[str], Optional[str]]:
    """Query existing QB Customer by DisplayName; create if missing.

    Returns (customer_id, display_name). Raises HTTPException(502) on transport failure.
    """
    display_name = (customer.full_name or "").strip() or (customer.company or "").strip() or "Customer"
    # Truncate to QB limits.
    display_name = display_name[:100]
    email = (customer.email or "").strip()
    phone = (customer.phone or "").strip()
    company = (customer.company or "").strip()

    # 1) Query existing.
    try:
        q = f"select * from Customer where DisplayName = '{display_name.replace(chr(39), chr(39)+chr(39))}'"
        resp = await client.get(
            f"{api_base}/v3/company/{realm_id}/query",
            headers=headers,
            params={"query": q, "minorversion": QB_MINOR_VERSION},
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="QuickBooks request failed")
    except Exception:
        raise HTTPException(status_code=502, detail="QuickBooks request failed")
    if resp.status_code == 200:
        try:
            body = resp.json()
            found = ((body.get("QueryResponse") or {}).get("Customer") or [])
            if found:
                cid = str(found[0].get("Id"))
                return cid, str(found[0].get("DisplayName") or display_name)
        except Exception:
            pass

    # 2) Create.
    payload: dict[str, Any] = {"DisplayName": display_name}
    if company:
        payload["CompanyName"] = company[:100]
    if email:
        payload["PrimaryEmailAddr"] = {"Address": email}
    if phone:
        payload["PrimaryPhone"] = {"FreeFormNumber": phone}
    try:
        create_resp = await client.post(
            f"{api_base}/v3/company/{realm_id}/customer",
            headers=headers,
            params={"minorversion": QB_MINOR_VERSION},
            json=payload,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="QuickBooks request failed")
    except Exception:
        raise HTTPException(status_code=502, detail="QuickBooks request failed")
    if create_resp.status_code in (200, 201):
        try:
            body = create_resp.json()
            created = body.get("Customer") or {}
            return str(created.get("Id")), str(created.get("DisplayName") or display_name)
        except Exception:
            return None, display_name
    return None, display_name


def _touch_synced(business_id=None, company_name: str | None = None):
    now = _utcnow_iso()
    _quickbooks_state["last_synced"] = now
    if business_id is not None:
        entry = _qb_tokens.get(str(business_id), {})
        entry["last_synced"] = now
        if company_name is not None:
            entry["company_name"] = company_name
        _qb_tokens[str(business_id)] = entry


# ─── OAuth ────────────────────────────────────────────────────────────

@router.get("/auth/url")
async def get_auth_url(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
):
    """Return the real Intuit OAuth2 authorization URL (URL building only; works keyless)."""
    client_id, _, redirect_uri, _ = _qb_settings()
    state = "qb"
    try:
        user = await _resolve_user(credentials, db) if db is not None else None
        if user is not None:
            state = str(user.id)
    except Exception:
        pass
    auth_url = (
        f"{QB_AUTH_BASE_URL}"
        f"?client_id={quote_plus(client_id or '')}"
        f"&redirect_uri={quote_plus(redirect_uri)}"
        f"&response_type=code"
        f"&scope={quote_plus(QB_SCOPES)}"
        f"&state={quote_plus(state)}"
    )
    return {"auth_url": auth_url}


@router.get("/callback")
async def qb_callback(
    code: str = Query(..., min_length=1),
    realmId: Optional[str] = Query(default=None),
    realm_id: Optional[str] = Query(default=None),
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
):
    """Exchange an OAuth code for tokens (Basic auth) and store per-business. 502 on failure."""
    _require_usable()
    realm = (realmId or realm_id or "").strip()
    if not realm:
        raise HTTPException(status_code=400, detail="realmId is required")

    client_id, client_secret, redirect_uri, _ = _qb_settings()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_resp = await client.post(
                QB_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="QuickBooks token exchange failed")
    except Exception:
        raise HTTPException(status_code=502, detail="QuickBooks token exchange failed")

    if token_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="QuickBooks token exchange failed")
    try:
        tokens = token_resp.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        expires_in = int(tokens.get("expires_in", 3600))
    except Exception:
        raise HTTPException(status_code=502, detail="QuickBooks token exchange failed")

    # Resolve business: prefer bearer identity, fall back to OAuth state (user id).
    current_user = await _resolve_user(credentials, db)
    business: Optional[Business] = None
    if current_user is not None:
        business = await _get_business(current_user, db)
    if business is None and state:
        try:
            from uuid import UUID as _UUID

            user_id = _UUID(str(state))
            result = await db.execute(select(User).where(User.id == user_id))
            state_user = result.scalar_one_or_none()
            if state_user is not None:
                business = await _get_business(state_user, db)
        except Exception:
            business = None
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    business_id = str(business.id)
    now = datetime.now(timezone.utc)
    _qb_tokens[business_id] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "realm_id": realm,
        "expires_at": now + timedelta(seconds=expires_in),
        "company_name": _qb_tokens.get(business_id, {}).get("company_name"),
        "last_synced": _qb_tokens.get(business_id, {}).get("last_synced"),
        "connected_at": _qb_tokens.get(business_id, {}).get("connected_at") or _utcnow_iso(),
    }
    _quickbooks_state["connected"] = True
    _quickbooks_state["last_synced"] = _qb_tokens[business_id].get("last_synced")
    return {"connected": True}


# ─── Status / disconnect ──────────────────────────────────────────────

@router.get("/status")
async def get_status(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
):
    """Return QuickBooks connection status (never calls Intuit)."""
    try:
        current_user = await _resolve_user(credentials, db)
        if current_user is not None:
            business = await _get_business(current_user, db)
            if business is not None:
                entry = _qb_tokens.get(str(business.id))
                if entry and entry.get("access_token"):
                    return {
                        "connected": True,
                        "company_name": entry.get("company_name"),
                        "last_synced": entry.get("last_synced"),
                    }
                return {"connected": False, "company_name": None, "last_synced": entry.get("last_synced") if entry else None}
        # Fallback global state (dev / unauthenticated).
        if _quickbooks_state.get("connected"):
            return {
                "connected": True,
                "company_name": _quickbooks_state.get("company_name"),
                "last_synced": _quickbooks_state.get("last_synced"),
            }
        return {"connected": False, "company_name": None, "last_synced": _quickbooks_state.get("last_synced")}
    except HTTPException:
        raise
    except Exception:
        return {"connected": False, "company_name": None, "last_synced": None}


@router.post("/disconnect")
async def disconnect(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
):
    """Clear QuickBooks connection state (per-business when known, else global). Always 200."""
    try:
        current_user = await _resolve_user(credentials, db) if db is not None else None
        if current_user is not None and db is not None:
            try:
                result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
                business = result.scalar_one_or_none()
                if business is not None:
                    _qb_tokens.pop(str(business.id), None)
            except Exception:
                pass
    except Exception:
        pass
    _quickbooks_state["connected"] = False
    _quickbooks_state["company_name"] = None
    _quickbooks_state["last_synced"] = None
    return {"disconnected": True, "connected": False}


# ─── Sync ─────────────────────────────────────────────────────────────

@router.post("/sync/invoices")
async def sync_invoices(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
):
    """Push local invoices to QuickBooks as Invoice entities (REAL v3 API)."""
    _require_usable()
    current_user = await _require_user(credentials, db)
    try:
        result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
        business = result.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    business_id = str(business.id)
    entry = _qb_tokens.get(business_id)
    if not entry or not entry.get("access_token") or not entry.get("realm_id"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)

    access_token = await _refresh_token_if_needed(business_id)
    realm_id = str(_qb_tokens[business_id]["realm_id"])
    api_base = _qb_api_base()
    headers = _qb_headers(access_token)

    try:
        inv_result = await db.execute(
            select(Invoice)
            .join(Customer, Invoice.customer_id == Customer.id)
            .where(Customer.business_id == business.id)
            .order_by(Invoice.created_at)
        )
        invoices = list(inv_result.scalars().all())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")

    synced = 0
    errors: list[dict[str, str]] = []
    try:
        http_client = httpx.AsyncClient(timeout=20)
    except Exception:
        raise HTTPException(status_code=502, detail="QuickBooks sync failed")

    async with http_client:
        for inv in invoices:
            try:
                cust_result = await db.execute(select(Customer).where(Customer.id == inv.customer_id))
                customer = cust_result.scalar_one_or_none()
                if customer is None:
                    errors.append({"invoice": getattr(inv, "invoice_number", "?"), "error": "Customer missing"})
                    continue
                qb_customer_id, qb_customer_name = await _qb_ensure_customer(
                    http_client, api_base, realm_id, headers, customer
                )
                if not qb_customer_id:
                    errors.append({"invoice": inv.invoice_number, "error": "Customer create failed"})
                    continue

                items_result = await db.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == inv.id))
                inv_items = list(items_result.scalars().all())

                lines: list[dict[str, Any]] = []
                for item in inv_items:
                    try:
                        qty = float(item.quantity or 0) or 1.0
                    except (TypeError, ValueError):
                        qty = 1.0
                    try:
                        rate = float(item.unit_price or 0)
                    except (TypeError, ValueError):
                        rate = 0.0
                    amount = round(qty * rate, 2)
                    lines.append(
                        {
                            "Amount": amount,
                            "DetailType": "SalesItemLineDetail",
                            "Description": (item.description or "")[:4000],
                            "SalesItemLineDetail": {
                                "ItemRef": {"value": "1", "name": "Services"},
                                "Qty": qty,
                                "UnitPrice": rate,
                            },
                        }
                    )
                if not lines:
                    try:
                        total = float(inv.total or 0)
                    except (TypeError, ValueError):
                        total = 0.0
                    lines.append(
                        {
                            "Amount": round(total, 2),
                            "DetailType": "SalesItemLineDetail",
                            "Description": f"Invoice {inv.invoice_number}",
                            "SalesItemLineDetail": {
                                "ItemRef": {"value": "1", "name": "Services"},
                                "Qty": 1,
                                "UnitPrice": round(total, 2),
                            },
                        }
                    )

                payload: dict[str, Any] = {
                    "CustomerRef": {"value": qb_customer_id, "name": qb_customer_name},
                    "Line": lines,
                    "DocNumber": inv.invoice_number,
                    "PrivateNote": f"VoiceField {inv.invoice_number}",
                    "CurrencyRef": {"value": (getattr(business, "currency", None) or "GBP")},
                }
                due = getattr(inv, "due_date", None)
                if isinstance(due, datetime):
                    payload["DueDate"] = due.strftime("%Y-%m-%d")

                resp = await http_client.post(
                    f"{api_base}/v3/company/{realm_id}/invoice",
                    headers=headers,
                    params={"minorversion": QB_MINOR_VERSION},
                    json=payload,
                )
            except HTTPException as he:
                if he.status_code == 502:
                    errors.append({"invoice": getattr(inv, "invoice_number", "?"), "error": "QuickBooks request failed"})
                    continue
                raise
            except Exception:
                errors.append({"invoice": getattr(inv, "invoice_number", "?"), "error": "QuickBooks request failed"})
                continue
            if resp.status_code in (200, 201):
                synced += 1
            else:
                errors.append({"invoice": inv.invoice_number, "error": f"QuickBooks rejected invoice ({resp.status_code})"})

    _touch_synced(business_id)
    return {"synced": synced, "errors": errors}


@router.post("/sync/contacts")
async def sync_contacts(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
):
    """Push local customers to QuickBooks as Customer entities (REAL v3 API)."""
    _require_usable()
    current_user = await _require_user(credentials, db)
    try:
        result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
        business = result.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    business_id = str(business.id)
    entry = _qb_tokens.get(business_id)
    if not entry or not entry.get("access_token") or not entry.get("realm_id"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)

    access_token = await _refresh_token_if_needed(business_id)
    realm_id = str(_qb_tokens[business_id]["realm_id"])
    api_base = _qb_api_base()
    headers = _qb_headers(access_token)

    try:
        cust_result = await db.execute(
            select(Customer).where(Customer.business_id == business.id).order_by(Customer.created_at)
        )
        customers = list(cust_result.scalars().all())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")

    synced = 0
    errors: list[dict[str, str]] = []
    try:
        http_client = httpx.AsyncClient(timeout=20)
    except Exception:
        raise HTTPException(status_code=502, detail="QuickBooks sync failed")

    async with http_client:
        for customer in customers:
            try:
                display_name = ((customer.full_name or "").strip() or (customer.company or "").strip() or "Customer")[:100]
                payload: dict[str, Any] = {"DisplayName": display_name}
                if (customer.company or "").strip():
                    payload["CompanyName"] = customer.company.strip()[:100]
                if (customer.email or "").strip():
                    payload["PrimaryEmailAddr"] = {"Address": customer.email.strip()}
                if (customer.phone or "").strip():
                    payload["PrimaryPhone"] = {"FreeFormNumber": customer.phone.strip()}
                resp = await http_client.post(
                    f"{api_base}/v3/company/{realm_id}/customer",
                    headers=headers,
                    params={"minorversion": QB_MINOR_VERSION},
                    json=payload,
                )
            except httpx.HTTPError:
                errors.append({"contact": customer.full_name, "error": "QuickBooks request failed"})
                continue
            except Exception:
                errors.append({"contact": customer.full_name, "error": "QuickBooks request failed"})
                continue
            if resp.status_code in (200, 201):
                synced += 1
            else:
                errors.append({"contact": customer.full_name, "error": f"QuickBooks rejected contact ({resp.status_code})"})

    _touch_synced(business_id)
    return {"synced": synced, "errors": errors}


@router.post("/sync/payments")
async def sync_payments(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
):
    """Push local payments to QuickBooks as Payment entities (REAL v3 API)."""
    _require_usable()
    current_user = await _require_user(credentials, db)
    try:
        result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
        business = result.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    business_id = str(business.id)
    entry = _qb_tokens.get(business_id)
    if not entry or not entry.get("access_token") or not entry.get("realm_id"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)

    access_token = await _refresh_token_if_needed(business_id)
    realm_id = str(_qb_tokens[business_id]["realm_id"])
    api_base = _qb_api_base()
    headers = _qb_headers(access_token)

    try:
        pay_result = await db.execute(
            select(Payment)
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .join(Customer, Invoice.customer_id == Customer.id)
            .where(Customer.business_id == business.id)
            .order_by(Payment.created_at)
        )
        payments = list(pay_result.scalars().all())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")

    synced = 0
    errors: list[dict[str, str]] = []
    try:
        http_client = httpx.AsyncClient(timeout=20)
    except Exception:
        raise HTTPException(status_code=502, detail="QuickBooks sync failed")

    async with http_client:
        for pay in payments:
            try:
                inv_result = await db.execute(select(Invoice).where(Invoice.id == pay.invoice_id))
                inv = inv_result.scalar_one_or_none()
                if inv is None:
                    errors.append({"payment": str(pay.id), "error": "Invoice missing"})
                    continue
                cust_result = await db.execute(select(Customer).where(Customer.id == inv.customer_id))
                customer = cust_result.scalar_one_or_none()
                if customer is None:
                    errors.append({"payment": str(pay.id), "error": "Customer missing"})
                    continue
                qb_customer_id, qb_customer_name = await _qb_ensure_customer(
                    http_client, api_base, realm_id, headers, customer
                )
                if not qb_customer_id:
                    errors.append({"payment": str(pay.id), "error": "Customer create failed"})
                    continue
                try:
                    total = float(pay.amount or 0)
                except (TypeError, ValueError):
                    total = 0.0
                payload: dict[str, Any] = {
                    "CustomerRef": {"value": qb_customer_id, "name": qb_customer_name},
                    "TotalAmt": round(total, 2),
                    "PrivateNote": f"VoiceField payment {pay.id}",
                    "CurrencyRef": {"value": (getattr(pay, "currency", None) or getattr(business, "currency", None) or "GBP")},
                }
                resp = await http_client.post(
                    f"{api_base}/v3/company/{realm_id}/payment",
                    headers=headers,
                    params={"minorversion": QB_MINOR_VERSION},
                    json=payload,
                )
            except HTTPException as he:
                if he.status_code == 502:
                    errors.append({"payment": str(pay.id), "error": "QuickBooks request failed"})
                    continue
                raise
            except Exception:
                errors.append({"payment": str(getattr(pay, 'id', '?')), "error": "QuickBooks request failed"})
                continue
            if resp.status_code in (200, 201):
                synced += 1
            else:
                errors.append({"payment": str(pay.id), "error": f"QuickBooks rejected payment ({resp.status_code})"})

    _touch_synced(business_id)
    return {"synced": synced, "errors": errors}


@router.get("/profit-loss")
async def profit_loss(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return P&L summary (GBP). Revenue = sum of paid invoice totals."""
    result = await db.execute(select(Invoice).where(Invoice.payment_status == PaymentStatus.PAID))
    invoices = result.scalars().all()
    revenue = float(sum(float(inv.total or 0) for inv in invoices))
    expenses = 0.0
    profit = revenue - expenses
    return {
        "period": "last_30_days",
        "revenue": revenue,
        "expenses": expenses,
        "profit": profit,
        "currency": "GBP",
    }
