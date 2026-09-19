import hmac
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import Webhook, WebhookDelivery, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
settings = get_settings()

WEBHOOK_EVENTS = [
    "job.created", "job.updated", "job.completed", "job.cancelled",
    "invoice.created", "invoice.paid", "invoice.overdue",
    "quote.created", "quote.accepted", "quote.rejected",
    "customer.created", "customer.updated",
    "payment.received", "payment.failed",
    "review.created",
]


@router.get("/events")
async def list_events():
    return {"events": WEBHOOK_EVENTS}


@router.post("/")
async def create_webhook(
    url: str,
    events: list[str],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    secret = hmac.new(
        settings.JWT_SECRET.encode(),
        url.encode(),
        hashlib.sha256
    ).hexdigest()[:32]

    webhook = Webhook(
        business_id=business.id,
        url=url,
        secret=secret,
        events=events,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    return {
        "id": str(webhook.id),
        "url": url,
        "events": events,
        "secret": secret,
    }


@router.get("/")
async def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    hooks_result = await db.execute(
        select(Webhook).where(Webhook.business_id == business.id)
    )
    return [
        {
            "id": str(w.id),
            "url": w.url,
            "events": w.events,
            "is_active": w.is_active,
            "last_triggered_at": w.last_triggered_at.isoformat() if w.last_triggered_at else None,
            "failure_count": w.failure_count,
        }
        for w in hooks_result.scalars().all()
    ]


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    biz_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.business_id == business.id,
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(webhook)
    await db.commit()
    return {"message": "Webhook deleted"}


@router.get("/{webhook_id}/deliveries")
async def list_deliveries(
    webhook_id: UUID,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    biz_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    hook_result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.business_id == business.id,
        )
    )
    if not hook_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Webhook not found")
    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": str(d.id),
            "event": d.event,
            "response_status": d.response_status,
            "success": d.success,
            "attempts": d.attempts,
            "created_at": d.created_at.isoformat(),
        }
        for d in result.scalars().all()
    ]


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a test event to a webhook"""
    biz_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.business_id == business.id,
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    import httpx
    payload = {
        "event": "webhook.test",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {"message": "This is a test webhook delivery"},
    }

    signature = hmac.new(
        webhook.secret.encode(),
        json.dumps(payload).encode(),
        hashlib.sha256
    ).hexdigest()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook.url,
                json=payload,
                headers={
                    "X-Webhook-Signature": signature,
                    "Content-Type": "application/json",
                },
                timeout=10,
            )

        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            event="webhook.test",
            payload=payload,
            response_status=response.status_code,
            success=200 <= response.status_code < 300,
            attempts=1,
        )
        db.add(delivery)
        await db.commit()

        return {"success": delivery.success, "status_code": response.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}
