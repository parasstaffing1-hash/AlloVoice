"""WhatsApp Cloud API integration (Meta Graph API v21.0).

Graceful degradation: when WHATSAPP_API_TOKEN / WHATSAPP_PHONE_NUMBER_ID are
not configured (no live keys), all send endpoints return 503 instead of failing.
Provider errors are mapped to clean 502 responses (never tracebacks).
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Business, Customer, Invoice, Job, Quote, User
from app.routes.auth import get_current_user
from app.services.phone import normalize_uk_phone

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])
settings = get_settings()

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

# ---------------------------------------------------------------------------
# In-memory inbound log (best-effort, process-local)
# ---------------------------------------------------------------------------
WEBHOOK_LOG: list[dict[str, Any]] = []
WEBHOOK_LOG_MAX = 200

# ---------------------------------------------------------------------------
# Approved templates catalogue
# ---------------------------------------------------------------------------
WHATSAPP_TEMPLATES: dict[str, dict[str, Any]] = {
    "quote_ready": {
        "name": "quote_ready",
        "language": "en_GB",
        "description": "Let a customer know their quote is ready to review.",
        "parameters": ["customer_name", "quote_number", "total", "quote_link"],
    },
    "invoice_due": {
        "name": "invoice_due",
        "language": "en_GB",
        "description": "Remind a customer that their invoice is due for payment.",
        "parameters": ["customer_name", "invoice_number", "total", "due_date", "payment_link"],
    },
    "engineer_on_way": {
        "name": "engineer_on_way",
        "language": "en_GB",
        "description": "Tell a customer their engineer is on the way.",
        "parameters": ["customer_name", "engineer_name", "eta", "tracking_link"],
    },
    "appointment_reminder": {
        "name": "appointment_reminder",
        "language": "en_GB",
        "description": "Remind a customer of an upcoming appointment.",
        "parameters": ["customer_name", "date", "time", "address"],
    },
}

JOB_STATUS_MESSAGES: dict[str, str] = {
    "scheduled": "Your appointment has been scheduled.",
    "confirmed": "Your appointment is confirmed.",
    "on_the_way": "Your engineer is on the way",
    "engineer_on_way": "Your engineer is on the way",
    "arrived": "Your engineer has arrived.",
    "in_progress": "Work on your job is now in progress.",
    "completed": "Your job has been completed. Thank you!",
    "cancelled": "Your job has been cancelled. Please contact us to reschedule.",
    "invoiced": "Your invoice is ready for payment.",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_PLACEHOLDER_MARKERS = (
    "your_",
    "your-",
    "placeholder",
    "example",
    "xxx",
    "changeme",
    "test_token",
    "dummy",
    "<",
    ">",
)
_EXACT_PLACEHOLDERS = {"", "test", "testing", "none", "null", "undefined", "0"}


def _looks_like_placeholder(value: str) -> bool:
    low = (value or "").strip().lower()
    if low in _EXACT_PLACEHOLDERS:
        return True
    return any(marker in low for marker in _PLACEHOLDER_MARKERS)


def _wa_usable() -> bool:
    """True when real WhatsApp Cloud API credentials are configured."""
    try:
        current = get_settings()
        token = str(getattr(current, "WHATSAPP_API_TOKEN", "") or "")
        phone_number_id = str(getattr(current, "WHATSAPP_PHONE_NUMBER_ID", "") or "")
    except Exception:
        return False
    if not token.strip() or not phone_number_id.strip():
        return False
    if _looks_like_placeholder(token) or _looks_like_placeholder(phone_number_id):
        return False
    return True


def _wa_verify_token() -> str:
    try:
        current = get_settings()
        configured = str(getattr(current, "WHATSAPP_VERIFY_TOKEN", "") or "").strip()
        if configured:
            return configured
    except Exception:
        pass
    return os.getenv("WHATSAPP_VERIFY_TOKEN", "voicefield") or "voicefield"


async def _wa_post(path_suffix: str, payload: dict[str, Any]) -> Optional[str]:
    """POST to the WhatsApp Cloud API. Returns the provider message id (if any).

    Raises HTTPException 502 for any provider/transport failure.
    """
    current = get_settings()
    token = str(getattr(current, "WHATSAPP_API_TOKEN", "") or "").strip()
    phone_number_id = str(getattr(current, "WHATSAPP_PHONE_NUMBER_ID", "") or "").strip()
    url = f"{GRAPH_BASE}/{phone_number_id}/{path_suffix.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except Exception as exc:
        logger.warning("WhatsApp provider request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="WhatsApp provider request failed")
    if resp.status_code >= 400:
        try:
            detail = (resp.text or "")[:300]
        except Exception:
            detail = ""
        logger.warning("WhatsApp provider error %s: %s", resp.status_code, detail)
        raise HTTPException(status_code=502, detail="WhatsApp provider error")
    try:
        data = resp.json()
        messages = data.get("messages") or []
        if isinstance(messages, list) and messages:
            message_id = messages[0].get("id")
            if message_id:
                return str(message_id)
    except Exception:
        pass
    return None


def _text_payload(to_e164: str, body: str) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": to_e164.lstrip("+"),
        "type": "text",
        "text": {"body": body, "preview_url": True},
    }


def _gbp(value: Any) -> str:
    try:
        return f"£{float(value):.2f}"
    except (TypeError, ValueError):
        return "£0.00"


def _normalize_customer_phone(customer: Customer) -> str:
    try:
        return normalize_uk_phone(customer.phone or "")
    except ValueError:
        raise HTTPException(status_code=422, detail="Customer has an invalid phone number")


async def _caller_business(db: AsyncSession, user: User) -> Business:
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if business is None:
        raise HTTPException(status_code=403, detail="No business found for current user")
    return business


def _ensure_customer_in_business(customer: Customer, business: Business) -> None:
    if customer.business_id != business.id:
        raise HTTPException(status_code=403, detail="Access denied to this customer")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SendMessageBody(BaseModel):
    phone_number: str
    message: str


class SendTemplateBody(BaseModel):
    phone_number: str
    template_name: str
    parameters: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Send endpoints
# ---------------------------------------------------------------------------
@router.post("/send-message")
async def send_whatsapp_message(
    body: SendMessageBody,
    current_user: User = Depends(get_current_user),
):
    """Send a free-form text message via the WhatsApp Cloud API."""
    text = (body.message or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Message must not be empty")
    try:
        normalized = normalize_uk_phone(body.phone_number)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UK phone number")
    if not _wa_usable():
        raise HTTPException(status_code=503, detail="WhatsApp is not configured")
    message_id = await _wa_post("messages", _text_payload(normalized, text))
    return {"success": True, "message_id": message_id}


@router.post("/send-quote")
async def send_quote_via_whatsapp(
    customer_id: UUID,
    quote_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a quote link + totals to the customer via WhatsApp."""
    business = await _caller_business(db, current_user)
    cust_result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    _ensure_customer_in_business(customer, business)

    quote_result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = quote_result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Quote not found for this customer")

    if not _wa_usable():
        raise HTTPException(status_code=503, detail="WhatsApp is not configured")
    to = _normalize_customer_phone(customer)

    app_url = settings.APP_URL.rstrip("/")
    link = f"{app_url}/quote/{quote_id}"
    message = (
        f"Hi {customer.full_name},\n\n"
        f"Your quote {quote.quote_number} is ready! "
        f"Total: {_gbp(quote.total)}.\n\n"
         f"View your quote here: {link}\n\n"
        f"Best regards,\nAllo Team"
    )
    message_id = await _wa_post("messages", _text_payload(to, message))
    return {
        "success": True,
        "message_id": message_id,
        "customer": customer.full_name,
        "phone": to,
        "quote_number": quote.quote_number,
    }


@router.post("/send-invoice")
async def send_invoice_via_whatsapp(
    customer_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send an invoice link + totals to the customer via WhatsApp."""
    business = await _caller_business(db, current_user)
    cust_result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    _ensure_customer_in_business(customer, business)

    inv_result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = inv_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Invoice not found for this customer")

    if not _wa_usable():
        raise HTTPException(status_code=503, detail="WhatsApp is not configured")
    to = _normalize_customer_phone(customer)

    app_url = settings.APP_URL.rstrip("/")
    link = f"{app_url}/portal"
    try:
        balance = float(invoice.total or 0) - float(invoice.amount_paid or 0)
    except (TypeError, ValueError):
        balance = 0.0
    message = (
        f"Hi {customer.full_name},\n\n"
        f"Your invoice {invoice.invoice_number} is ready for payment. "
        f"Total: {_gbp(invoice.total)}, balance due: {_gbp(balance)}.\n\n"
        f"View and pay your invoice here: {link}\n\n"
         f"Thank you for your business!\n\n"
        f"Best regards,\nAllo Team"
    )
    message_id = await _wa_post("messages", _text_payload(to, message))
    return {
        "success": True,
        "message_id": message_id,
        "customer": customer.full_name,
        "phone": to,
        "invoice_number": invoice.invoice_number,
    }


@router.post("/send-job-update")
async def send_job_update_whatsapp(
    customer_id: UUID,
    job_id: UUID,
    status: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a job status update to the customer via WhatsApp."""
    business = await _caller_business(db, current_user)
    cust_result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    _ensure_customer_in_business(customer, business)

    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Job not found for this customer")

    if not _wa_usable():
        raise HTTPException(status_code=503, detail="WhatsApp is not configured")
    to = _normalize_customer_phone(customer)

    status_text = JOB_STATUS_MESSAGES.get((status or "").strip().lower(), f"Job status update: {status}")
    app_url = settings.APP_URL.rstrip("/")
    message = (
        f"Hi {customer.full_name},\n\n"
        f"{status_text}.\n\n"
         f"Track your job: {app_url}/track/{job_id}\n\n"
        f"Best regards,\nAllo Team"
    )
    message_id = await _wa_post("messages", _text_payload(to, message))
    return {
        "success": True,
        "message_id": message_id,
        "customer": customer.full_name,
        "phone": to,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
@router.get("/templates")
async def list_templates():
    """List approved WhatsApp template names with their parameter schema."""
    return {"templates": list(WHATSAPP_TEMPLATES.values())}


@router.post("/send-template")
async def send_template_message(
    body: SendTemplateBody,
    current_user: User = Depends(get_current_user),
):
    """Send an approved template message via the WhatsApp Cloud API."""
    spec = WHATSAPP_TEMPLATES.get((body.template_name or "").strip())
    if spec is None:
        raise HTTPException(status_code=400, detail=f"Unknown template: {body.template_name}")
    try:
        normalized = normalize_uk_phone(body.phone_number)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UK phone number")
    if not _wa_usable():
        raise HTTPException(status_code=503, detail="WhatsApp is not configured")

    params = [str(p) for p in (body.parameters or [])]
    template_obj: dict[str, Any] = {
        "name": spec["name"],
        "language": {"code": spec.get("language", "en_GB")},
    }
    if params:
        template_obj["components"] = [
            {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}
        ]
    payload = {
        "messaging_product": "whatsapp",
        "to": normalized.lstrip("+"),
        "type": "template",
        "template": template_obj,
    }
    message_id = await _wa_post("messages", payload)
    return {"success": True, "message_id": message_id, "template": spec["name"]}


# ---------------------------------------------------------------------------
# Webhook (Meta verification + inbound) — no auth (called by Meta)
# ---------------------------------------------------------------------------
@router.get("/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
):
    """Meta webhook verification handshake."""
    expected = _wa_verify_token()
    if hub_mode == "subscribe" and hub_verify_token == expected and hub_challenge is not None:
        try:
            return PlainTextResponse(str(int(hub_challenge)))
        except (TypeError, ValueError):
            return PlainTextResponse(str(hub_challenge))
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    """Receive inbound WhatsApp events. Always 200; parses best-effort."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        entries = body.get("entry", []) if isinstance(body, dict) else []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                value = change.get("value") or {}
                if not isinstance(value, dict):
                    continue
                for msg in value.get("messages") or []:
                    if not isinstance(msg, dict):
                        continue
                    text_body = ""
                    text_obj = msg.get("text") or {}
                    if isinstance(text_obj, dict):
                        text_body = str(text_obj.get("body") or "")[:500]
                    WEBHOOK_LOG.append(
                        {
                            "received_at": datetime.now(timezone.utc).isoformat(),
                            "from": msg.get("from"),
                            "id": msg.get("id"),
                            "type": msg.get("type"),
                            "body": text_body,
                        }
                    )
                    if len(WEBHOOK_LOG) > WEBHOOK_LOG_MAX:
                        del WEBHOOK_LOG[: len(WEBHOOK_LOG) - WEBHOOK_LOG_MAX]
    except Exception as exc:
        logger.warning("WhatsApp webhook parse failed: %s", type(exc).__name__)
    return {"success": True}


@router.get("/webhook-log")
async def webhook_log(current_user: User = Depends(get_current_user)):
    """Return recent inbound webhook messages (auth required)."""
    return {
        "success": True,
        "count": len(WEBHOOK_LOG),
        "logs": list(reversed(WEBHOOK_LOG[-50:])),
    }
