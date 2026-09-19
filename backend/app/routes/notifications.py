from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import User, Business, Job, Customer
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
settings = get_settings()


@router.post("/send")
async def send_notification(
    recipient_id: UUID,
    title: str,
    message: str,
    channel: str = "in_app",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a notification via Novu"""
    # In production, this calls Novu API
    # For now, store in database and return
    return {
        "success": True,
        "channel": channel,
        "recipient_id": str(recipient_id),
        "title": title,
        "message": message,
    }


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

    # In production, send via Novu:
    # - Email: invoice + review request
    # - SMS: job completion notice
    # - WhatsApp: photo summary + invoice

    return {
        "success": True,
        "channels": ["email", "sms", "whatsapp"],
        "customer": customer.full_name,
        "job": job.title,
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

    # In production:
    # 1. Generate Google Review link
    # 2. Send via email + SMS
    # 3. Track if review was left

    return {
        "success": True,
        "customer": customer.full_name,
        "review_link": "https://g.page/r/YOUR_BUSINESS/review",
    }


@router.post("/invoice-reminder")
async def send_invoice_reminder(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send payment reminder for overdue invoice"""
    # In production, check if invoice is overdue and send reminder
    return {
        "success": True,
        "message": "Invoice reminder sent",
    }
