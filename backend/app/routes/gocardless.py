"""GoCardless Direct Debit for customer invoices.

Real flow (sandbox-ready) with graceful degradation: no live keys exist
in this region, so every GoCardless API call is guarded by
:func:`_gc_usable`. When the access token is missing (or a placeholder
containing "xxx"), mutating endpoints return HTTP 503 instead of calling
GoCardless, and tracebacks are never leaked.

Implemented with raw httpx (``gocardless_pro`` is not installed here) against
https://api-sandbox.gocardless.com (sandbox) /
https://api.gocardless.com (live), Bearer token.

``payments.py`` owns ``/api/payments``; this module owns ``/api/gocardless``.
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Business, Customer, Invoice, Payment, User
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gocardless", tags=["gocardless"])
settings = get_settings()

GC_SANDBOX_BASE = "https://api-sandbox.gocardless.com"
GC_LIVE_BASE = "https://api.gocardless.com"
GC_API_VERSION = "2015-07-06"

NOT_CONFIGURED_DETAIL = "GoCardless not configured — add GOCARDLESS_ACCESS_TOKEN"
NO_MANDATE_DETAIL = "No mandate — complete redirect flow first"

# In-memory Direct Debit state (no new tables).
# _MANDATES: customer_id (str) -> {"mandate_id": str, "customer_id": str}
# _PAYMENTS: gocardless payment id (str) -> {"payment_id", "invoice_id",
#   "customer_id", "status", "charge_date"}
_MANDATES: dict[str, dict] = {}
_PAYMENTS: dict[str, dict] = {}


class CompleteFlowRequest(BaseModel):
    redirect_flow_id: str
    session_token: Optional[str] = None


def _gc_token() -> str:
    try:
        token = getattr(settings, "GOCARDLESS_ACCESS_TOKEN", "") or ""
    except Exception:
        token = ""
    if not token:
        token = os.getenv("GOCARDLESS_ACCESS_TOKEN", "")
    return (token or "").strip()


def _gc_usable() -> bool:
    """True only when a real access token is configured.

    A token counts as usable when it is non-empty and not a placeholder
    (placeholders contain "xxx", e.g. the sandbox placeholder in .env).
    """
    token = _gc_token()
    return bool(token) and "xxx" not in token.lower()


def _gc_environment() -> str:
    try:
        env = (getattr(settings, "GOCARDLESS_ENVIRONMENT", "") or "").strip().lower()
    except Exception:
        env = ""
    if not env:
        env = (os.getenv("GOCARDLESS_ENVIRONMENT", "") or "").strip().lower()
    return env or "sandbox"


def _gc_base_url() -> str:
    return GC_LIVE_BASE if _gc_environment() == "live" else GC_SANDBOX_BASE


def _gc_headers() -> dict:
    return {
        "Authorization": f"Bearer {_gc_token()}",
        "GoCardless-Version": GC_API_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "VoiceField/2.0",
    }


def _client() -> httpx.AsyncClient:
    """Configured async HTTP client for the GoCardless API."""
    return httpx.AsyncClient(
        base_url=_gc_base_url(), headers=_gc_headers(), timeout=20.0
    )


def _gc_webhook_secret() -> str:
    try:
        secret = getattr(settings, "GOCARDLESS_WEBHOOK_SECRET", "") or ""
    except Exception:
        secret = ""
    if not secret:
        secret = os.getenv("GOCARDLESS_WEBHOOK_SECRET", "")
    return (secret or "").strip()


def _amount_pence(invoice: Invoice) -> int:
    """Invoice total in minor units (pence)."""
    return int(round(float(invoice.total) * 100))


def _is_paid(invoice: Invoice) -> bool:
    status = getattr(invoice.payment_status, "value", invoice.payment_status)
    return str(status) == "paid"


async def _get_owned_invoice(
    invoice_id: UUID, current_user: User, db: AsyncSession
) -> tuple:
    """Load an invoice and verify it belongs to the caller's business.

    Chain: Invoice -> Customer (invoice.customer_id) ->
    Business (customer.business_id); 404 unless
    business.owner_id == current_user.id.
    """
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    customer: Optional[Customer] = None
    if invoice.customer_id:
        c_result = await db.execute(
            select(Customer).where(Customer.id == invoice.customer_id)
        )
        customer = c_result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    b_result = await db.execute(
        select(Business).where(Business.id == customer.business_id)
    )
    business = b_result.scalar_one_or_none()
    if business is None or business.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return invoice, customer


async def _get_business(current_user: User, db: AsyncSession) -> Optional[Business]:
    result = await db.execute(
        select(Business).where(Business.owner_id == current_user.id)
    )
    return result.scalar_one_or_none()


def _charge_date_plus_3d() -> str:
    """Next working day-ish charge date: today + 3 days (YYYY-MM-DD)."""
    return (date.today() + timedelta(days=3)).isoformat()


async def _mark_invoice_paid_gc(
    invoice: Invoice, gc_payment_id: Optional[str], db: AsyncSession
) -> bool:
    """Mark an invoice paid + record a Payment row. Idempotent: skip if paid."""
    if _is_paid(invoice):
        return False
    invoice.payment_status = "paid"
    invoice.paid_at = datetime.utcnow()
    invoice.payment_method = "gocardless"
    invoice.amount_paid = invoice.total
    ref = str(gc_payment_id)[:255] if gc_payment_id else None
    if ref and not invoice.gocardless_payment_id:
        invoice.gocardless_payment_id = ref
    payment = Payment(
        invoice_id=invoice.id,
        amount=invoice.total,
        currency="GBP",
        payment_method="gocardless",
        gocardless_payment_id=ref,
        transaction_id=ref,
        status="completed",
        notes="GoCardless Direct Debit",
    )
    db.add(payment)
    await db.commit()
    return True


@router.post("/redirect-flow")
async def create_redirect_flow(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a GoCardless redirect flow for an invoice.

    Returns ``{redirect_url, flow_id}`` for the customer to authorise
    a Direct Debit mandate. 503 when GoCardless is not configured.
    """
    invoice, _customer = await _get_owned_invoice(invoice_id, current_user, db)
    if not _gc_usable():
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_DETAIL)

    try:
        app_url = getattr(settings, "APP_URL", "") or os.getenv(
            "APP_URL", "http://localhost:3002"
        )
        payload = {
            "redirect_flows": {
                "description": f"Invoice {invoice.invoice_number} £{float(invoice.total):.2f}",
                "session_token": str(invoice.id),
                "success_redirect_url": f"{app_url}/portal?dd=success",
            }
        }
        async with _client() as client:
            resp = await client.post("/redirect_flows", json=payload)
        if resp.status_code >= 400:
            logger.warning(
                "GoCardless redirect_flows create failed: %s %s",
                resp.status_code,
                resp.text[:500],
            )
            raise HTTPException(status_code=502, detail="GoCardless request failed")
        data = resp.json().get("redirect_flows") or resp.json().get("data") or {}
        flow_id = data.get("id")
        redirect_url = data.get("redirect_url")
        if not flow_id or not redirect_url:
            logger.warning("GoCardless redirect flow unexpected shape: %s", str(data)[:500])
            raise HTTPException(status_code=502, detail="GoCardless request failed")
        return {"redirect_url": redirect_url, "flow_id": flow_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("GoCardless redirect flow failed")
        raise HTTPException(status_code=502, detail="GoCardless request failed")


@router.post("/complete-flow")
async def complete_redirect_flow(
    body: CompleteFlowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Complete a redirect flow → mandate. Stores mandate keyed by customer id.

    Returns ``{mandate_id, customer_id}``. 503 when GoCardless is not configured.
    """
    if not _gc_usable():
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_DETAIL)

    flow_id = (body.redirect_flow_id or "").strip()
    if not flow_id:
        raise HTTPException(status_code=422, detail="redirect_flow_id is required")

    session_token = (body.session_token or "").strip()
    try:
        # If the caller did not supply the session token (the invoice id we
        # used at creation), try to discover it from the redirect flow.
        if not session_token:
            try:
                async with _client() as client:
                    fetched = await client.get(f"/redirect_flows/{flow_id}")
                if fetched.status_code < 400:
                    fdata = fetched.json().get("redirect_flows") or {}
                    session_token = str(fdata.get("session_token") or "").strip()
            except Exception:
                logger.warning("GoCardless redirect flow fetch failed; continuing")
        try:
            async with _client() as client:
                resp = await client.post(
                    f"/redirect_flows/{flow_id}/actions/complete",
                    json={"data": {"session_token": session_token}},
                )
        except Exception:
            logger.exception("GoCardless redirect flow complete failed")
            raise HTTPException(status_code=502, detail="GoCardless request failed")
        if resp.status_code >= 400:
            logger.warning(
                "GoCardless redirect flow complete failed: %s %s",
                resp.status_code,
                resp.text[:500],
            )
            raise HTTPException(status_code=502, detail="GoCardless request failed")
        data = resp.json().get("redirect_flows") or resp.json().get("data") or {}
        links = data.get("links") or {}
        mandate_id = links.get("mandate") or data.get("mandate")
        token_from_gc = str(data.get("session_token") or session_token or "").strip()
        if not mandate_id:
            logger.warning("GoCardless complete unexpected shape: %s", str(data)[:500])
            raise HTTPException(status_code=502, detail="GoCardless request failed")

        # Resolve the customer via session_token (= invoice id) with tenancy check.
        customer_id: Optional[str] = None
        if token_from_gc:
            try:
                inv_uuid = UUID(str(token_from_gc))
            except ValueError:
                inv_uuid = None
            if inv_uuid is not None:
                invoice, customer = await _get_owned_invoice(
                    inv_uuid, current_user, db
                )
                customer_id = str(customer.id)
        if not customer_id:
            raise HTTPException(status_code=404, detail="Invoice not found")

        _MANDATES[customer_id] = {
            "mandate_id": str(mandate_id),
            "customer_id": customer_id,
        }
        return {"mandate_id": str(mandate_id), "customer_id": customer_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("GoCardless complete flow failed")
        raise HTTPException(status_code=502, detail="GoCardless request failed")


@router.post("/collect")
async def collect_payment(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Collect an invoice via an existing Direct Debit mandate.

    400 when no mandate exists for the invoice's customer; 503 when
    GoCardless is not configured. Returns ``{payment_id, status, charge_date}``.
    """
    invoice, customer = await _get_owned_invoice(invoice_id, current_user, db)
    mandate = _MANDATES.get(str(customer.id))
    if not mandate:
        raise HTTPException(status_code=400, detail=NO_MANDATE_DETAIL)
    if not _gc_usable():
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_DETAIL)

    mandate_id = mandate.get("mandate_id")
    charge_date = _charge_date_plus_3d()
    try:
        payload = {
            "payments": {
                "amount": _amount_pence(invoice),
                "currency": "GBP",
                "links": {"mandate": mandate_id},
                "metadata": {"invoice_id": str(invoice.id)},
                "charge_date": charge_date,
            }
        }
        try:
            async with _client() as client:
                resp = await client.post("/payments", json=payload)
        except Exception:
            logger.exception("GoCardless payment create failed")
            raise HTTPException(status_code=502, detail="GoCardless request failed")
        if resp.status_code >= 400:
            logger.warning(
                "GoCardless payment create failed: %s %s",
                resp.status_code,
                resp.text[:500],
            )
            raise HTTPException(status_code=502, detail="GoCardless request failed")
        data = resp.json().get("payments") or resp.json().get("data") or {}
        payment_id = data.get("id")
        status = data.get("status", "pending")
        charge_date_resp = data.get("charge_date") or charge_date
        if not payment_id:
            logger.warning("GoCardless payment unexpected shape: %s", str(data)[:500])
            raise HTTPException(status_code=502, detail="GoCardless request failed")

        _PAYMENTS[str(payment_id)] = {
            "payment_id": str(payment_id),
            "invoice_id": str(invoice.id),
            "customer_id": str(customer.id),
            "status": str(status),
            "charge_date": str(charge_date_resp),
        }
        try:
            invoice.gocardless_payment_id = str(payment_id)[:255]
            await db.commit()
        except Exception:
            logger.warning("Could not persist gocardless_payment_id", exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass
        return {
            "payment_id": str(payment_id),
            "status": str(status),
            "charge_date": str(charge_date_resp),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("GoCardless collect failed")
        raise HTTPException(status_code=502, detail="GoCardless request failed")


@router.get("/mandates")
async def list_mandates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List in-memory mandates belonging to the caller's business customers."""
    business = await _get_business(current_user, db)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    result = await db.execute(
        select(Customer.id).where(Customer.business_id == business.id)
    )
    owned_ids = {str(row) for (row,) in result.all()}
    mandates = [m for cid, m in _MANDATES.items() if cid in owned_ids]
    return {"mandates": mandates}


@router.post("/gc-webhook")
async def gc_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """GoCardless webhook receiver. Always 200 — never 500.

    Verifies HMAC-SHA256 ``Webhook-Signature`` against
    ``GOCARDLESS_WEBHOOK_SECRET`` when set; when empty, accepts the event
    but logs a warning. Handles payment confirmed/failed → updates the local
    Invoice payment_status + Payment row.
    """
    try:
        raw = await request.body()
    except Exception:
        logger.warning("GC webhook: could not read body")
        return {"received": True}

    secret = _gc_webhook_secret()
    try:
        sig = request.headers.get("Webhook-Signature") or request.headers.get(
            "webhook-signature"
        ) or ""
    except Exception:
        sig = ""

    if secret:
        if not sig:
            logger.warning("GC webhook: missing signature")
            return {"received": True}
        try:
            expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, (sig or "").strip()):
                logger.warning("GC webhook: signature mismatch")
                return {"received": True}
        except Exception:
            logger.warning("GC webhook: signature verification error", exc_info=True)
            return {"received": True}
    else:
        logger.warning(
            "GOCARDLESS_WEBHOOK_SECRET not set — accepting webhook without verification"
        )

    try:
        payload = json.loads((raw or b"").decode("utf-8") or "{}")
    except Exception:
        logger.warning("GC webhook: invalid JSON body")
        return {"received": True}

    try:
        events = payload.get("events") or []
        if not isinstance(events, list):
            return {"received": True}
        for ev in events:
            if not isinstance(ev, dict):
                continue
            try:
                await _handle_gc_event(ev, db)
            except Exception:
                logger.exception("GC webhook: event handling failed")
                try:
                    await db.rollback()
                except Exception:
                    pass
                continue
    except Exception:
        logger.exception("GC webhook handling failed")
    return {"received": True}


async def _handle_gc_event(ev: dict, db: AsyncSession) -> None:
    resource_type = str(ev.get("resource_type") or "")
    action = str(ev.get("action") or "")
    if resource_type != "payments":
        return
    links = ev.get("links") or {}
    metadata = ev.get("metadata") or {}
    gc_payment_id = links.get("payment") or ev.get("id")
    invoice_id_str = metadata.get("invoice_id")

    if action in ("confirmed", "paid_out"):
        invoice = None
        if invoice_id_str:
            try:
                inv_uuid = UUID(str(invoice_id_str))
            except ValueError:
                inv_uuid = None
            if inv_uuid is not None:
                result = await db.execute(
                    select(Invoice).where(Invoice.id == inv_uuid)
                )
                invoice = result.scalar_one_or_none()
        if invoice is None and gc_payment_id:
            rec = _PAYMENTS.get(str(gc_payment_id))
            if rec and rec.get("invoice_id"):
                try:
                    inv_uuid = UUID(str(rec["invoice_id"]))
                    result = await db.execute(
                        select(Invoice).where(Invoice.id == inv_uuid)
                    )
                    invoice = result.scalar_one_or_none()
                except ValueError:
                    invoice = None
            if invoice is None:
                result = await db.execute(
                    select(Invoice).where(
                        Invoice.gocardless_payment_id == str(gc_payment_id)
                    )
                )
                invoice = result.scalar_one_or_none()
        if invoice is None:
            logger.warning(
                "GC webhook: confirmed payment %s has no matching invoice",
                gc_payment_id,
            )
            return
        marked = await _mark_invoice_paid_gc(invoice, gc_payment_id, db)
        if marked and gc_payment_id:
            rec = _PAYMENTS.get(str(gc_payment_id))
            if rec:
                rec["status"] = "confirmed"
        logger.info(
            "GC webhook: invoice %s marked paid (payment %s)",
            invoice.id,
            gc_payment_id,
        )
    elif action in ("failed", "cancelled", "charged_back", "chargeback_cancelled"):
        logger.warning(
            "GC webhook: payment %s %s", gc_payment_id or "unknown", action
        )
        if gc_payment_id and str(gc_payment_id) in _PAYMENTS:
            _PAYMENTS[str(gc_payment_id)]["status"] = action
    else:
        logger.info("GC webhook: ignoring payments event action=%s", action)


@router.get("/status")
async def gc_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GoCardless configuration status."""
    configured = _gc_usable()
    environment = _gc_environment()
    try:
        business = await _get_business(current_user, db)
        if business is not None:
            result = await db.execute(
                select(Customer.id).where(Customer.business_id == business.id)
            )
            owned_ids = {str(row) for (row,) in result.all()}
            count = sum(1 for cid in _MANDATES if cid in owned_ids)
        else:
            count = len(_MANDATES)
    except Exception:
        logger.warning("GC status mandates count failed", exc_info=True)
        count = len(_MANDATES)
    return {
        "configured": configured,
        "environment": environment,
        "mandates_count": count,
    }
