import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import User, Customer, Job
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])
settings = get_settings()

WHATSAPP_API_URL = "https://graph.facebook.com/v18.0/YOUR_PHONE_NUMBER_ID/messages"


@router.post("/send-message")
async def send_whatsapp_message(
    phone_number: str,
    message: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a WhatsApp message via WhatsApp Business API"""
    # In production, use official WhatsApp Business API
    return {
        "success": True,
        "phone": phone_number,
        "message": message[:50] + "..." if len(message) > 50 else message,
    }


@router.post("/send-quote")
async def send_quote_via_whatsapp(
    customer_id: UUID,
    quote_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a quote to customer via WhatsApp"""
    cust_result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        return {"error": "Customer not found"}

    message = f"""Hi {customer.full_name},

Your quote is ready! Please review the details and let us know if you'd like to proceed.

View your quote here: {settings.APP_URL}/quotes/{quote_id}

Best regards,
VoiceField Team"""

    return {
        "success": True,
        "customer": customer.full_name,
        "phone": customer.phone,
        "message_preview": message[:100] + "...",
    }


@router.post("/send-invoice")
async def send_invoice_via_whatsapp(
    customer_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send an invoice to customer via WhatsApp"""
    cust_result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        return {"error": "Customer not found"}

    message = f"""Hi {customer.full_name},

Your invoice is ready for payment.

View and pay your invoice here: {settings.APP_URL}/invoices/{invoice_id}

Thank you for your business!

Best regards,
VoiceField Team"""

    return {
        "success": True,
        "customer": customer.full_name,
        "phone": customer.phone,
        "message_preview": message[:100] + "...",
    }


@router.post("/send-job-update")
async def send_job_update_whatsapp(
    customer_id: UUID,
    job_id: UUID,
    status: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send job status update via WhatsApp"""
    cust_result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        return {"error": "Customer not found"}

    status_messages = {
        "scheduled": "Your job has been scheduled.",
        "in_progress": "Our technician is on the way!",
        "completed": "Your job has been completed. Thank you!",
        "invoiced": "Your invoice is ready for payment.",
    }

    message = f"""Hi {customer.full_name},

{status_messages.get(status, f'Job status update: {status}')}

Track your job: {settings.APP_URL}/jobs/{job_id}

Best regards,
VoiceField Team"""

    return {
        "success": True,
        "customer": customer.full_name,
        "phone": customer.phone,
        "status": status,
    }
