"""Xero accounting integration for VoiceField (UK field service SaaS, GBP focus).

Hardened, mock-testable design (no live keys required):

- Degrades gracefully when XERO_CLIENT_ID / XERO_CLIENT_SECRET are missing,
  empty, or obvious placeholders: live endpoints return HTTP 503 with a clean
  message instead of calling Xero. Tracebacks are never leaked.
- OAuth2 authorization URL builder + code exchange against the Xero Identity
  service (basic auth id:secret). All network failures surface as HTTP 502
  with a clean message.
- Per-business connection state kept in module-level dicts keyed by business
  id (str). Nothing here alters SQLAlchemy models; the pre-existing
  ``Business.xero_*`` / ``Invoice.xero_*`` columns are updated best-effort
  where they already exist.
- Tenancy: sync endpoints resolve the caller's business via
  ``select(Business).where(Business.owner_id == current_user.id)`` and only
  ever touch that business's rows.
- Invoice sync pushes unsynced local invoices (``xero_invoice_id IS NULL``)
  as Xero ACCREC invoices. Note: the local ``Invoice`` model carries a
  ``payment_status`` enum (pending/paid/overdue/...) and no
  sent/authorised-style status, so "unsynced" is the sync filter.
  VAT is UK 20%%: ``LineAmountTypes=Exclusive`` with a per-line ``TaxAmount``
  at 20%%. ``TaxType`` is deliberately omitted so Xero applies its default
  UK sales tax rate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Business, Customer, Invoice, InvoiceItem, User
from app.routes.auth import get_current_user
from app.services.auth import decode_access_token

router = APIRouter(prefix="/api/xero", tags=["xero"])

XERO_AUTH_URL = "https://login.xero.com/identity/connect/authorize"
XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"
XERO_API_URL = "https://api.xero.com/api.xro/2.0"

XERO_SCOPES = (
    "openid profile email accounting.transactions accounting.contacts offline_access"
)

NOT_CONNECTED_DETAIL = "Xero not connected \u2014 add XERO_* keys and connect"
NOT_AUTHORISED_DETAIL = "Xero not connected \u2014 complete OAuth connect first"

# Placeholder markers: values containing any of these (case-insensitive) are
# treated as "no real key configured", as is any empty/blank value.
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

# Connection state keyed by business id (str) ->
# {access_token, refresh_token, tenant_id, tenant_name, expires_at, last_synced}
_XERO_TOKENS: dict[str, dict[str, Any]] = {}
# Synced-tracking fallback keyed by business id (str) -> set of row id strs.
# (The Invoice model has no boolean xero_synced column, so module state tracks
# what this process has pushed; xero_invoice_id/xero_synced_at columns are
# still updated best-effort where the live API returns an id.)
_SYNCED_INVOICE_IDS: dict[str, set[str]] = {}
_SYNCED_CONTACT_IDS: dict[str, set[str]] = {}

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


def _xero_usable() -> bool:
    """True only when a real (non-empty, non-placeholder) id+secret are set."""
    try:
        settings = get_settings()
        client_id = str(settings.XERO_CLIENT_ID or "")
        client_secret = str(settings.XERO_CLIENT_SECRET or "")
    except Exception:
        return False
    if not client_id.strip() or not client_secret.strip():
        return False
    if _looks_placeholder(client_id) or _looks_placeholder(client_secret):
        return False
    return True


def _require_usable() -> None:
    if not _xero_usable():
        raise HTTPException(status_code=503, detail=NOT_CONNECTED_DETAIL)


def _redirect_uri() -> str:
    try:
        settings = get_settings()
        configured = str(settings.XERO_REDIRECT_URI or "").strip()
        if configured:
            return configured
        app_url = str(settings.APP_URL or "http://localhost:3002").rstrip("/")
    except Exception:
        app_url = "http://localhost:3002"
    return f"{app_url}/settings?tab=integrations"


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
    """Best-effort user lookup; returns None instead of raising."""
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
    """Caller's owned business, or None (never raises)."""
    try:
        result = await db.execute(
            select(Business).where(Business.owner_id == current_user.id)
        )
        return result.scalar_one_or_none()
    except Exception:
        return None


async def _get_token(business: Any) -> str:
    """Return a valid Xero access token for a business.

    Auto-refreshes via grant_type=refresh_token when the stored token is
    missing/expiring/expired. Network or protocol failures raise HTTP 502
    with a clean message (no traceback leak).
    """
    business_id = str(getattr(business, "id", business))
    entry = _XERO_TOKENS.get(business_id)
    if not entry or not entry.get("refresh_token"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)

    expires_at = _as_aware(entry.get("expires_at"))
    now = datetime.now(timezone.utc)
    if (
        entry.get("access_token")
        and expires_at is not None
        and expires_at > now + timedelta(seconds=60)
    ):
        return str(entry["access_token"])

    settings = get_settings()
    client_id = str(settings.XERO_CLIENT_ID or "")
    client_secret = str(settings.XERO_CLIENT_SECRET or "")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                XERO_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": entry["refresh_token"],
                },
                auth=(client_id, client_secret),
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Xero token refresh failed")
    except Exception:
        raise HTTPException(status_code=502, detail="Xero token refresh failed")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Xero token refresh failed")
    try:
        data = resp.json()
        access_token = data["access_token"]
        refresh_token = data.get("refresh_token") or entry["refresh_token"]
        expires_in = int(data.get("expires_in", 1800))
    except Exception:
        raise HTTPException(status_code=502, detail="Xero token refresh failed")

    entry["access_token"] = access_token
    entry["refresh_token"] = refresh_token
    entry["expires_at"] = now + timedelta(seconds=expires_in)
    _XERO_TOKENS[business_id] = entry
    return str(access_token)


def _build_invoice_payload(
    inv: Invoice,
    customer: Optional[Customer],
    items: list[InvoiceItem],
    business: Business,
) -> dict[str, Any]:
    name = None
    email = None
    if customer is not None:
        name = (customer.full_name or "").strip() or None
        if not name and (customer.company or "").strip():
            name = customer.company.strip()
        email = (customer.email or "").strip() or None
    contact: dict[str, Any] = {"Name": name or "Customer"}
    if email:
        contact["EmailAddress"] = email

    lines: list[dict[str, Any]] = []
    for item in items or []:
        try:
            qty = float(item.quantity or 0)
        except (TypeError, ValueError):
            qty = 0.0
        try:
            unit = float(item.unit_price or 0)
        except (TypeError, ValueError):
            unit = 0.0
        lines.append(
            {
                "Description": item.description or "",
                "Quantity": qty,
                "UnitAmount": unit,
                # UK 20% VAT; TaxType omitted so Xero applies its default.
                "TaxAmount": round(qty * unit * 0.20, 2),
                "AccountCode": "200",
            }
        )
    if not lines:
        try:
            subtotal = float(inv.subtotal or 0)
        except (TypeError, ValueError):
            subtotal = 0.0
        lines.append(
            {
                "Description": f"Invoice {inv.invoice_number}",
                "Quantity": 1,
                "UnitAmount": subtotal,
                "TaxAmount": round(subtotal * 0.20, 2),
                "AccountCode": "200",
            }
        )

    created = getattr(inv, "created_at", None)
    due = getattr(inv, "due_date", None)
    payload: dict[str, Any] = {
        "Type": "ACCREC",
        "Contact": contact,
        "InvoiceNumber": inv.invoice_number,
        "Date": created.strftime("%Y-%m-%d") if isinstance(created, datetime) else datetime.utcnow().strftime("%Y-%m-%d"),
        "LineAmountTypes": "Exclusive",
        "LineItems": lines,
        "Status": "AUTHORISED",
        "CurrencyCode": (getattr(business, "currency", None) or "GBP"),
    }
    if isinstance(due, datetime):
        payload["DueDate"] = due.strftime("%Y-%m-%d")
    return payload


def _build_contact_payload(customer: Customer) -> dict[str, Any]:
    name = (customer.full_name or "").strip() or (customer.company or "").strip() or "Customer"
    payload: dict[str, Any] = {"Name": name}
    if (customer.email or "").strip():
        payload["EmailAddress"] = customer.email.strip()
    phones: list[dict[str, Any]] = []
    if (customer.phone or "").strip():
        phones.append({"PhoneType": "MOBILE", "PhoneNumber": customer.phone.strip()})
    if phones:
        payload["Phones"] = phones
    return payload


# ─── OAuth ────────────────────────────────────────────────────────────

@router.get("/auth")
async def xero_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Return the Xero OAuth consent URL (works keyless; never calls Xero."""
    try:
        settings = get_settings()
        client_id = str(settings.XERO_CLIENT_ID or "")
    except Exception:
        client_id = ""
    # Embed the user id in state so the browser callback (no auth header)
    # can resolve which business is connecting. Falls back to "xero".
    state = "xero"
    try:
        user = await _resolve_user(credentials, db)
        if user is not None:
            state = str(user.id)
    except Exception:
        pass
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "scope": XERO_SCOPES,
        "state": state,
    }
    return {"auth_url": f"{XERO_AUTH_URL}?{urlencode(params)}"}


@router.get("/callback")
async def xero_callback(
    code: str,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
):
    """Exchange an OAuth code for tokens and store them for the business."""
    _require_usable()

    settings = get_settings()
    client_id = str(settings.XERO_CLIENT_ID or "")
    client_secret = str(settings.XERO_CLIENT_SECRET or "")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                XERO_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _redirect_uri(),
                },
                auth=(client_id, client_secret),
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Xero token exchange failed")
    except Exception:
        raise HTTPException(status_code=502, detail="Xero token exchange failed")

    if token_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Xero token exchange failed")
    try:
        tokens = token_response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        expires_in = int(tokens.get("expires_in", 1800))
    except Exception:
        raise HTTPException(status_code=502, detail="Xero token exchange failed")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            connections_response = await client.get(
                XERO_CONNECTIONS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Xero connection lookup failed")
    except Exception:
        raise HTTPException(status_code=502, detail="Xero connection lookup failed")

    if connections_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Xero connection lookup failed")
    try:
        connections = connections_response.json()
        tenant_id = connections[0]["tenantId"]
        tenant_name = connections[0].get("tenantName")
    except Exception:
        raise HTTPException(status_code=502, detail="No Xero organisation found")

    # Resolve the business: prefer the bearer identity, fall back to the
    # OAuth `state` (browser redirects carry no Authorization header).
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
    _XERO_TOKENS[business_id] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        "last_synced": _XERO_TOKENS.get(business_id, {}).get("last_synced"),
    }

    # Best-effort persist to the pre-existing Business columns (never fatal).
    try:
        business.xero_tenant_id = tenant_id
        business.xero_access_token = access_token
        business.xero_refresh_token = refresh_token
        business.xero_token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    if credentials is None:
        # Browser flow (no auth header on redirects): send them back to
        # settings UI with a success flag instead of raw JSON.
        try:
            app_url = str(get_settings().APP_URL or "http://localhost:3002").rstrip("/")
        except Exception:
            app_url = "http://localhost:3002"
        return RedirectResponse(
            f"{app_url}/settings?tab=integrations&xero=connected", status_code=302
        )
    return {"connected": True}


# ─── Sync ─────────────────────────────────────────────────────────────

@router.post("/sync-invoices")
async def sync_invoices_to_xero(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> dict[str, Any]:
    """Push unsynced local invoices to Xero as ACCREC invoices."""
    # Usability gate first so keyless callers always see 503 (even unauthenticated).
    _require_usable()
    current_user = await _require_user(credentials, db)

    try:
        result = await db.execute(
            select(Business).where(Business.owner_id == current_user.id)
        )
        business = result.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    business_id = str(business.id)
    entry = _XERO_TOKENS.get(business_id)
    if not entry or not entry.get("tenant_id"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)

    access_token = await _get_token(business)
    tenant_id = str(entry["tenant_id"])

    try:
        inv_result = await db.execute(
            select(Invoice)
            .join(Customer, Invoice.customer_id == Customer.id)
            .where(
                Customer.business_id == business.id,
                Invoice.xero_invoice_id.is_(None),
            )
            .order_by(Invoice.created_at)
        )
        invoices = list(inv_result.scalars().all())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")

    synced_ids = _SYNCED_INVOICE_IDS.setdefault(business_id, set())
    synced = 0
    errors: list[dict[str, str]] = []

    try:
        http_client = httpx.AsyncClient(timeout=20)
    except Exception:
        raise HTTPException(status_code=502, detail="Xero sync failed")

    async with http_client:
        for inv in invoices:
            if str(inv.id) in synced_ids:
                continue
            try:
                items_result = await db.execute(
                    select(InvoiceItem).where(InvoiceItem.invoice_id == inv.id)
                )
                inv_items = list(items_result.scalars().all())
                cust_result = await db.execute(
                    select(Customer).where(Customer.id == inv.customer_id)
                )
                customer = cust_result.scalar_one_or_none()
                payload = _build_invoice_payload(inv, customer, inv_items, business)
                resp = await http_client.post(
                    f"{XERO_API_URL}/Invoices",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Xero-Tenant-Id": tenant_id,
                        "Content-Type": "application/json",
                    },
                    json={"Invoices": [payload]},
                )
            except httpx.HTTPError:
                errors.append(
                    {"invoice": inv.invoice_number, "error": "Xero request failed"}
                )
                continue
            except Exception:
                errors.append(
                    {"invoice": inv.invoice_number, "error": "Xero request failed"}
                )
                continue

            if resp.status_code in (200, 201):
                xero_id: Optional[str] = None
                try:
                    body = resp.json()
                    returned = (body.get("Invoices") or [{}])[0]
                    xero_id = returned.get("InvoiceID")
                except Exception:
                    xero_id = None
                try:
                    if xero_id:
                        inv.xero_invoice_id = str(xero_id)
                    inv.xero_synced_at = datetime.utcnow()
                    synced_ids.add(str(inv.id))
                    synced += 1
                except Exception:
                    errors.append(
                        {"invoice": inv.invoice_number, "error": "Local mark-synced failed"}
                    )
                    continue
            else:
                errors.append(
                    {
                        "invoice": inv.invoice_number,
                        "error": f"Xero rejected invoice ({resp.status_code})",
                    }
                )

    try:
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="Database unavailable")

    entry["last_synced"] = _utcnow_iso()
    return {"synced": synced, "errors": errors}


@router.post("/sync-contacts")
async def sync_contacts_to_xero(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> dict[str, Any]:
    """Push local customers to Xero as contacts."""
    _require_usable()
    current_user = await _require_user(credentials, db)

    try:
        result = await db.execute(
            select(Business).where(Business.owner_id == current_user.id)
        )
        business = result.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    business_id = str(business.id)
    entry = _XERO_TOKENS.get(business_id)
    if not entry or not entry.get("tenant_id"):
        raise HTTPException(status_code=400, detail=NOT_AUTHORISED_DETAIL)

    access_token = await _get_token(business)
    tenant_id = str(entry["tenant_id"])

    try:
        cust_result = await db.execute(
            select(Customer)
            .where(Customer.business_id == business.id)
            .order_by(Customer.created_at)
        )
        customers = list(cust_result.scalars().all())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Database unavailable")

    synced_ids = _SYNCED_CONTACT_IDS.setdefault(business_id, set())
    synced = 0
    errors: list[dict[str, str]] = []

    try:
        http_client = httpx.AsyncClient(timeout=20)
    except Exception:
        raise HTTPException(status_code=502, detail="Xero sync failed")

    async with http_client:
        for customer in customers:
            if str(customer.id) in synced_ids:
                continue
            try:
                payload = _build_contact_payload(customer)
                resp = await http_client.post(
                    f"{XERO_API_URL}/Contacts",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Xero-Tenant-Id": tenant_id,
                        "Content-Type": "application/json",
                    },
                    json={"Contacts": [payload]},
                )
            except httpx.HTTPError:
                errors.append(
                    {"contact": customer.full_name, "error": "Xero request failed"}
                )
                continue
            except Exception:
                errors.append(
                    {"contact": customer.full_name, "error": "Xero request failed"}
                )
                continue

            if resp.status_code in (200, 201):
                synced_ids.add(str(customer.id))
                synced += 1
            else:
                errors.append(
                    {
                        "contact": customer.full_name,
                        "error": f"Xero rejected contact ({resp.status_code})",
                    }
                )

    entry["last_synced"] = _utcnow_iso()
    return {"synced": synced, "errors": errors}


# ─── Status / disconnect ──────────────────────────────────────────────

@router.get("/status")
async def xero_status(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> dict[str, Any]:
    """Return Xero connection state from module state (never calls Xero)."""
    try:
        current_user = await _resolve_user(credentials, db)
        if current_user is None:
            return {"connected": False}
        business = await _get_business(current_user, db)
        if business is None:
            return {"connected": False}
        entry = _XERO_TOKENS.get(str(business.id))
        if not entry or not entry.get("access_token"):
            return {"connected": False}
        return {
            "connected": True,
            "tenant_name": entry.get("tenant_name"),
            "last_synced": entry.get("last_synced"),
        }
    except HTTPException:
        raise
    except Exception:
        return {"connected": False}


@router.post("/disconnect")
async def xero_disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Clear the calling business's Xero tokens."""
    try:
        result = await db.execute(
            select(Business).where(Business.owner_id == current_user.id)
        )
        business = result.scalar_one_or_none()
        if business is not None:
            business_id = str(business.id)
            _XERO_TOKENS.pop(business_id, None)
            _SYNCED_INVOICE_IDS.pop(business_id, None)
            _SYNCED_CONTACT_IDS.pop(business_id, None)
            try:
                business.xero_tenant_id = None
                business.xero_access_token = None
                business.xero_refresh_token = None
                business.xero_token_expires = None
                await db.commit()
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Xero disconnect failed")
    return {"connected": False, "disconnected": True}


# ─── Legacy prefix aliases ────────────────────────────────────────────
# The router moved from /api/integrations/xero to /api/xero; keep the old
# paths working on the same router (absolute paths bypass the router prefix).

_LEGACY_ALIASES: tuple[tuple[str, Any, list[str]], ...] = (
    ("/api/integrations/xero/auth", xero_auth, ["GET"]),
    ("/api/integrations/xero/callback", xero_callback, ["GET"]),
    ("/api/integrations/xero/sync-invoices", sync_invoices_to_xero, ["POST"]),
    ("/api/integrations/xero/sync-contacts", sync_contacts_to_xero, ["POST"]),
    ("/api/integrations/xero/status", xero_status, ["GET"]),
    ("/api/integrations/xero/disconnect", xero_disconnect, ["POST"]),
)

for _alias_path, _alias_endpoint, _alias_methods in _LEGACY_ALIASES:
    router.routes.append(
        APIRoute(
            path=_alias_path,
            endpoint=_alias_endpoint,
            methods=_alias_methods,
            include_in_schema=False,
        )
    )
del _alias_path, _alias_endpoint, _alias_methods
