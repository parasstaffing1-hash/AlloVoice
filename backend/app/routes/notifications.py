import os
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional
from uuid import UUID

import httpx

from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import User, Business, Job, Customer
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
settings = get_settings()

NOVU_FALLBACK_URL = "https://api.novu.co"


def _novu_creds():
    """Return (api_key, base_url). Key blank => keyless/simulated mode."""
    try:
        cfg = get_settings()
        cfg_key = (getattr(cfg, "NOVU_API_KEY", "") or "").strip()
        cfg_url = (getattr(cfg, "NOVU_API_URL", "") or "").strip()
    except Exception:
        cfg_key, cfg_url = "", ""
    key = (os.getenv("NOVU_API_KEY") or cfg_key or "").strip()
    base = (os.getenv("NOVU_API_URL") or cfg_url or "").strip() or NOVU_FALLBACK_URL
    return key, base.rstrip("/")


async def _trigger_novu(
    *, event_name: str, subscriber_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Trigger a Novu workflow. Never raises; keyless => simulated."""
    api_key, base_url = _novu_creds()
    if not api_key:
        return {"status": "simulated", "event": event_name}
    url = f"{base_url}/v1/events/trigger"
    body = {
        "name": event_name,
        "to": {"subscriberId": subscriber_id},
        "payload": payload,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"ApiKey {api_key}"},
                json=body,
            )
        if 200 <= resp.status_code < 300:
            try:
                data = resp.json()
            except Exception:
                data = {}
            return {"status": "sent", "event": event_name, "response": data}
        return {
            "status": "failed",
            "event": event_name,
            "error": f"Novu HTTP {resp.status_code}: {resp.text[:500]}",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "event": event_name,
            "error": f"{type(exc).__name__}: {exc}",
        }


@router.post("/send")
async def send_notification(
    recipient_id: UUID,
    title: str,
    message: str,
    channel: str = "in_app",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a notification via Novu (real trigger when NOVU_API_KEY set, else simulated)."""
    event_name = (channel or "in_app").strip() or "in_app"
    try:
        result = await _trigger_novu(
            event_name=event_name,
            subscriber_id=str(recipient_id),
            payload={"title": title, "message": message, "channel": channel},
        )
    except Exception as exc:
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    status_value = str(result.get("status") or "simulated")
    response = {
        "success": True,
        "channel": channel,
        "recipient_id": str(recipient_id),
        "title": title,
        "message": message,
        "status": status_value,
    }
    if status_value == "failed":
        response["error"] = str(result.get("error") or "Novu trigger failed")[:1000]
    return response


@router.post("/job-completion")
async def notify_job_completion(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send job completion notifications to customer"""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        return {"error": "Job not found"}

    # Get customer
    cust_result = await db.execute(select(Customer).where(Customer.id == job.customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        return {"error": "Customer not found"}

    # Novu: email (invoice + review request), SMS, WhatsApp summary.
    try:
        novu_result = await _trigger_novu(
            event_name="job-completion",
            subscriber_id=str(customer.id),
            payload={
                "customer": customer.full_name,
                "job": job.title,
                "job_id": str(job.id),
                "channels": ["email", "sms", "whatsapp"],
            },
        )
    except Exception as exc:
        novu_result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    return {
        "success": True,
        "channels": ["email", "sms", "whatsapp"],
        "customer": customer.full_name,
        "job": job.title,
        "status": str(novu_result.get("status") or "simulated"),
    }


@router.post("/review-request")
async def send_review_request(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send Google Review request to customer"""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        return {"error": "Job not found"}

    cust_result = await db.execute(select(Customer).where(Customer.id == job.customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        return {"error": "Customer not found"}

    try:
        novu_result = await _trigger_novu(
            event_name="review-request",
            subscriber_id=str(customer.id),
            payload={
                "customer": customer.full_name,
                "job_id": str(job.id),
                "review_link": "https://g.page/r/YOUR_BUSINESS/review",
            },
        )
    except Exception as exc:
        novu_result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    return {
        "success": True,
        "customer": customer.full_name,
        "review_link": "https://g.page/r/YOUR_BUSINESS/review",
        "status": str(novu_result.get("status") or "simulated"),
    }


@router.post("/invoice-reminder")
async def send_invoice_reminder(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send payment reminder for overdue invoice"""
    try:
        novu_result = await _trigger_novu(
            event_name="invoice-reminder",
            subscriber_id=str(current_user.id),
            payload={"invoice_id": str(invoice_id)},
        )
    except Exception as exc:
        novu_result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "success": True,
        "message": "Invoice reminder sent",
        "status": str(novu_result.get("status") or "simulated"),
    }
