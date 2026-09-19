"""QuickBooks Online integration for VoiceField (UK field service SaaS).

Stub implementation (GBP / UK focus):
- OAuth2 authorization URL builder (stub, handles missing env gracefully).
- Module-level in-memory connection state + per-business OAuth token store.
- Invoice / contact / payment sync stubs that count local rows.
- Stub profit & loss summary derived from paid local invoices.

In production the sync endpoints would push to the QBO Accounting API
(https://quickbooks.api.intuit.com) using stored OAuth2 tokens.
"""

import os
from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Business, Customer, Invoice, Payment, PaymentStatus, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/quickbooks", tags=["quickbooks"])

QB_AUTH_BASE_URL = "https://appcenter.intuit.com/connect/oauth2"
QB_SCOPES = "com.intuit.quickbooks.accounting"

# Module-level connection state (global fallback for single-tenant dev/stub).
_quickbooks_state: dict = {
    "connected": False,
    "company_name": None,
    "last_synced": None,
}

# OAuth tokens keyed by business id (str) -> token dict.
# e.g. {str(business_id): {"access_token": ..., "refresh_token": ..., "company_name": ..., "connected_at": ...}}
_qb_tokens: dict[str, dict] = {}


def _get_client_id() -> str:
    """Return QB client id from env or a placeholder (never crash on missing env)."""
    try:
        settings = get_settings()
        client_id = getattr(settings, "QB_CLIENT_ID", None) or os.getenv("QB_CLIENT_ID")
    except Exception:
        client_id = os.getenv("QB_CLIENT_ID")
    if not client_id:
        client_id = os.getenv("QB_CLIENT_ID", "QB_CLIENT_ID_PLACEHOLDER")
    if not client_id:
        client_id = "QB_CLIENT_ID_PLACEHOLDER"
    return client_id


def _get_app_url() -> str:
    """Return APP_URL from settings or a safe default."""
    try:
        settings = get_settings()
        app_url = getattr(settings, "APP_URL", None) or os.getenv("APP_URL")
    except Exception:
        app_url = os.getenv("APP_URL")
    if not app_url:
        app_url = "http://localhost:3002"
    return str(app_url).rstrip("/")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_business_id(current_user: User, db: AsyncSession):
    """Best-effort business lookup; returns None instead of raising for stubs."""
    try:
        result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
        business = result.scalar_one_or_none()
        return business.id if business else None
    except Exception:
        return None


@router.get("/auth/url")
async def get_auth_url(current_user: User = Depends(get_current_user)):
    """Return QuickBooks OAuth2 authorization URL (stub)."""
    client_id = _get_client_id()
    app_url = _get_app_url()
    redirect_uri = app_url + "/settings?tab=integrations&provider=quickbooks&code=DEMO"
    auth_url = (
        f"{QB_AUTH_BASE_URL}"
        f"?client_id={quote_plus(client_id)}"
        f"&redirect_uri={quote_plus(redirect_uri)}"
        f"&response_type=code"
        f"&scope={quote_plus(QB_SCOPES)}"
        f"&state={quote_plus(str(current_user.id))}"
    )
    return {"auth_url": auth_url}


@router.get("/status")
async def get_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return QuickBooks connection status."""
    business_id = await _get_business_id(current_user, db)
    if business_id is not None:
        tokens = _qb_tokens.get(str(business_id))
        if tokens:
            return {
                "connected": True,
                "company_name": tokens.get("company_name"),
                "last_synced": tokens.get("last_synced"),
            }
    return {
        "connected": bool(_quickbooks_state.get("connected", False)),
        "company_name": _quickbooks_state.get("company_name"),
        "last_synced": _quickbooks_state.get("last_synced"),
    }


@router.post("/disconnect")
async def disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear QuickBooks connection state."""
    business_id = await _get_business_id(current_user, db)
    if business_id is not None:
        _qb_tokens.pop(str(business_id), None)
    _quickbooks_state["connected"] = False
    _quickbooks_state["company_name"] = None
    _quickbooks_state["last_synced"] = None
    return {"disconnected": True}


def _touch_synced(business_id=None, company_name: str | None = None):
    """Update module-level last_synced timestamps."""
    now = _utcnow_iso()
    _quickbooks_state["last_synced"] = now
    # Keep connected flag as-is; sync implies a (stub) connection.
    if business_id is not None:
        entry = _qb_tokens.get(str(business_id), {})
        entry["last_synced"] = now
        if company_name is not None:
            entry["company_name"] = company_name
        _qb_tokens[str(business_id)] = entry


@router.post("/sync/invoices")
async def sync_invoices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync all local invoices to QuickBooks (stub: counts rows).

    In production this would push each invoice to the QBO API.
    """
    result = await db.execute(select(Invoice))
    invoices = result.scalars().all()
    synced = len(invoices)
    business_id = await _get_business_id(current_user, db)
    _touch_synced(business_id)
    return {"synced": synced, "errors": []}


@router.post("/sync/contacts")
async def sync_contacts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync all local customers to QuickBooks as contacts (stub: counts rows).

    In production this would push each customer to the QBO API.
    """
    result = await db.execute(select(Customer))
    customers = result.scalars().all()
    synced = len(customers)
    business_id = await _get_business_id(current_user, db)
    _touch_synced(business_id)
    return {"synced": synced, "errors": []}


@router.post("/sync/payments")
async def sync_payments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync all local payments to QuickBooks (stub: counts rows).

    In production this would push each payment to the QBO API.
    """
    result = await db.execute(select(Payment))
    payments = result.scalars().all()
    synced = len(payments)
    business_id = await _get_business_id(current_user, db)
    _touch_synced(business_id)
    return {"synced": synced, "errors": []}


@router.get("/profit-loss")
async def profit_loss(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return stub P&L summary (GBP).

    Revenue = sum of paid invoice totals. Expenses are 0.0 in this stub.
    """
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
