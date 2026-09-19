"""Stripe card payments for customer invoices.

Graceful degradation: no live keys exist in the dev region, so every
Stripe call is guarded by :func:`_stripe_usable`. When the secret key is
missing (or a placeholder containing "xxx"), card endpoints return
HTTP 503 instead of calling Stripe, and tracebacks are never leaked.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Business, Customer, Invoice, Payment, User
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])
settings = get_settings()

stripe.api_key = settings.STRIPE_SECRET_KEY

NOT_CONFIGURED_DETAIL = "Card payments not configured — add STRIPE_* keys"


def _stripe_usable() -> bool:
    """True only when a real secret key is configured.

    A key counts as usable when it is non-empty and not a placeholder
    (placeholders contain "xxx").
    """
    key = (settings.STRIPE_SECRET_KEY or "").strip()
    return bool(key) and "xxx" not in key.lower()


def _amount_pence(invoice: Invoice) -> int:
    """Invoice total in minor units (pence), rounding half-even."""
    return int(round(float(invoice.total) * 100))


def _is_paid(invoice: Invoice) -> bool:
    status = getattr(invoice.payment_status, "value", invoice.payment_status)
    return str(status) == "paid"


def _obj_get(obj, key, default=None):
    """Best-effort getter for dicts, StripeObjects, and plain objects."""
    try:
        get = getattr(obj, "get", None)
        if callable(get):
            return get(key, default)
    except Exception:
        pass
    try:
        return obj[key]
    except Exception:
        return getattr(obj, key, default)


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


async def _mark_invoice_paid(
    invoice: Invoice, stripe_ref, db: AsyncSession
) -> bool:
    """Mark an invoice paid + record a Payment row. Idempotent: skip if paid."""
    if _is_paid(invoice):
        return False
    invoice.payment_status = "paid"
    invoice.paid_at = datetime.utcnow()
    invoice.payment_method = "card"
    ref = str(stripe_ref)[:255] if stripe_ref else None
    if ref and not invoice.stripe_payment_intent_id:
        invoice.stripe_payment_intent_id = ref
    payment = Payment(
        invoice_id=invoice.id,
        amount=invoice.total,
        payment_method="card",
        stripe_payment_id=ref,
        status="completed",
    )
    db.add(payment)
    await db.commit()
    return True


def _checkout_kwargs(invoice: Invoice, customer: Optional[Customer], invoice_id: UUID) -> dict:
    kwargs: dict = {
        "mode": "payment",
        "line_items": [
            {
                "price_data": {
                    "currency": "gbp",
                    "product_data": {"name": f"Invoice {invoice.invoice_number}"},
                    "unit_amount": _amount_pence(invoice),
                },
                "quantity": 1,
            }
        ],
        "metadata": {"invoice_id": str(invoice_id)},
        "success_url": f"{settings.APP_URL}/portal?paid={invoice_id}",
        "cancel_url": f"{settings.APP_URL}/portal",
    }
    if customer is not None and getattr(customer, "email", None):
        kwargs["customer_email"] = customer.email
    return kwargs


@router.post("/create-payment-intent")
async def create_payment_intent(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    invoice, customer = await _get_owned_invoice(invoice_id, current_user, db)
    if not _stripe_usable():
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_DETAIL)

    stripe.api_key = settings.STRIPE_SECRET_KEY
    intent_kwargs: dict = {
        "amount": _amount_pence(invoice),
        "currency": "gbp",
        "metadata": {"invoice_id": str(invoice_id)},
        "automatic_payment_methods": {"enabled": True},
    }
    if customer is not None and getattr(customer, "email", None):
        intent_kwargs["receipt_email"] = customer.email
    try:
        intent = stripe.PaymentIntent.create(**intent_kwargs)
    except Exception:
        logger.exception("Stripe PaymentIntent.create failed")
        raise HTTPException(status_code=502, detail="Stripe request failed")

    invoice.stripe_payment_intent_id = _obj_get(intent, "id")
    await db.commit()
    return {
        "client_secret": _obj_get(intent, "client_secret"),
        "payment_intent_id": _obj_get(intent, "id"),
    }


@router.post("/create-checkout-session")
async def create_checkout_session(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stripe Checkout Session for an invoice (powers email/SMS pay links)."""
    invoice, customer = await _get_owned_invoice(invoice_id, current_user, db)
    if not _stripe_usable():
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_DETAIL)

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(
            **_checkout_kwargs(invoice, customer, invoice_id)
        )
    except Exception:
        logger.exception("Stripe Checkout Session.create failed")
        raise HTTPException(status_code=502, detail="Stripe request failed")
    return {"checkout_url": _obj_get(session, "url")}


@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if not sig:
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event_type = event["type"]
    except Exception:
        event_type = getattr(event, "type", None)
    try:
        data_obj = event["data"]["object"]
    except Exception:
        data_obj = _obj_get(_obj_get(event, "data", {}), "object", {}) or {}

    if event_type == "payment_intent.succeeded":
        metadata = _obj_get(data_obj, "metadata", {}) or {}
        invoice_id_str = _obj_get(metadata, "invoice_id")
        stripe_pid = _obj_get(data_obj, "id")
        if invoice_id_str:
            try:
                inv_uuid = UUID(str(invoice_id_str))
            except ValueError:
                return {"received": True}
            result = await db.execute(select(Invoice).where(Invoice.id == inv_uuid))
            invoice = result.scalar_one_or_none()
            if invoice is not None:
                await _mark_invoice_paid(invoice, stripe_pid, db)
        return {"received": True}

    if event_type == "checkout.session.completed":
        metadata = _obj_get(data_obj, "metadata", {}) or {}
        invoice_id_str = _obj_get(metadata, "invoice_id")
        stripe_ref = _obj_get(data_obj, "payment_intent") or _obj_get(data_obj, "id")
        if invoice_id_str:
            try:
                inv_uuid = UUID(str(invoice_id_str))
            except ValueError:
                return {"received": True}
            result = await db.execute(select(Invoice).where(Invoice.id == inv_uuid))
            invoice = result.scalar_one_or_none()
            if invoice is not None:
                await _mark_invoice_paid(invoice, stripe_ref, db)
        return {"received": True}

    if event_type == "payment_intent.payment_failed":
        logger.warning(
            "Stripe payment failed: %s", _obj_get(data_obj, "id", "unknown")
        )
        return {"received": True}

    return {"received": True}


@router.post("/gocardless/create-mandate")
async def create_gocardless_mandate(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GoCardless Direct Debit stub — honestly reports it is not configured."""
    invoice, _customer = await _get_owned_invoice(invoice_id, current_user, db)
    return {
        "status": "not_configured",
        "message": "GoCardless is not configured — Direct Debit unavailable",
        "invoice_id": str(invoice.id),
    }


@router.get("/payment-link/{invoice_id}")
async def create_payment_link(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    invoice, customer = await _get_owned_invoice(invoice_id, current_user, db)
    if not _stripe_usable():
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_DETAIL)

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        link = stripe.PaymentLink.create(
            line_items=[
                {
                    "price_data": {
                        "currency": "gbp",
                        "product_data": {"name": f"Invoice {invoice.invoice_number}"},
                        "unit_amount": _amount_pence(invoice),
                    },
                    "quantity": 1,
                }
            ],
            metadata={"invoice_id": str(invoice_id)},
        )
        return {"payment_link": _obj_get(link, "url")}
    except Exception:
        logger.exception("Stripe PaymentLink.create failed; trying Checkout Session")

    try:
        session = stripe.checkout.Session.create(
            **_checkout_kwargs(invoice, customer, invoice_id)
        )
        return {"payment_link": _obj_get(session, "url")}
    except Exception:
        logger.exception("Stripe Checkout fallback failed; returning portal URL")
        return {"payment_link": f"{settings.APP_URL}/portal"}


@router.get("/config")
async def get_payment_config(current_user: User = Depends(get_current_user)):
    return {
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY or None,
        "configured": _stripe_usable(),
    }
