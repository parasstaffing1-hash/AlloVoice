import resend
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import EmailLog, Business, User, Invoice, Quote, Customer
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/emails", tags=["emails"])
settings = get_settings()


def _resend_key() -> str:
    # Read at send time (not import time) so env changes apply without reimport.
    return (get_settings().RESEND_API_KEY or "").strip()


@router.post("/send")
async def send_email(
    to: str,
    subject: str,
    html: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a transactional email via Resend"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()

    if not _resend_key():
        raise HTTPException(status_code=503, detail="Email not configured (RESEND_API_KEY missing)")

    try:
        resend.api_key = _resend_key()
        email_response = resend.Emails.send({
            "from": get_settings().EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "html": html,
        })

        log = EmailLog(
            business_id=business.id if business else None,
            to_email=to,
            subject=subject,
            resend_id=email_response.get("id") if isinstance(email_response, dict) else None,
            status="sent",
            sent_at=datetime.utcnow(),
        )
        db.add(log)
        await db.commit()

        return {"success": True, "id": email_response.get("id") if isinstance(email_response, dict) else None}
    except Exception as e:
        log = EmailLog(
            business_id=business.id if business else None,
            to_email=to,
            subject=subject,
            status="failed",
        )
        db.add(log)
        await db.commit()
        return {"success": False, "error": str(e)}


@router.post("/send-invoice/{invoice_id}")
async def send_invoice_email(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send invoice email to customer"""
    inv_result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = inv_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    cust_result = await db.execute(select(Customer).where(Customer.id == invoice.customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer or not customer.email:
        raise HTTPException(status_code=400, detail="Customer has no email")

    html = f"""
    <h2>Invoice {invoice.invoice_number}</h2>
    <p>Hi {customer.full_name},</p>
    <p>Your invoice for <strong>£{invoice.total:.2f}</strong> is ready.</p>
    <p>Due date: {invoice.due_date.strftime('%d/%m/%Y') if invoice.due_date else 'N/A'}</p>
    <p><a href="{settings.APP_URL}/invoices/{invoice.id}" style="background:#6b21a8;color:white;padding:12px 24px;border-radius:8px;text-decoration:none">View & Pay</a></p>
    """

    return await send_email(customer.email, f"Invoice {invoice.invoice_number}", html, current_user, db)


@router.post("/send-quote/{quote_id}")
async def send_quote_email(
    quote_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send quote email to customer"""
    q_result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = q_result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    cust_result = await db.execute(select(Customer).where(Customer.id == quote.customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer or not customer.email:
        raise HTTPException(status_code=400, detail="Customer has no email")

    html = f"""
    <h2>Quote {quote.quote_number}</h2>
    <p>Hi {customer.full_name},</p>
    <p>Your quote for <strong>£{quote.total:.2f}</strong> is ready.</p>
    <p>Valid until: {quote.valid_until.strftime('%d/%m/%Y') if quote.valid_until else 'N/A'}</p>
    <p><a href="{settings.APP_URL}/quotes/{quote.id}" style="background:#6b21a8;color:white;padding:12px 24px;border-radius:8px;text-decoration:none">View & Accept</a></p>
    """

    return await send_email(customer.email, f"Quote {quote.quote_number}", html, current_user, db)


@router.get("/logs")
async def list_email_logs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    biz_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = biz_result.scalar_one_or_none()
    if not business:
        return []
    result = await db.execute(
        select(EmailLog)
        .where(EmailLog.business_id == business.id)
        .order_by(EmailLog.created_at.desc())
        .limit(100)
    )
    return [
        {
            "id": str(log.id),
            "to": log.to_email,
            "subject": log.subject,
            "status": log.status,
            "created_at": log.created_at.isoformat(),
        }
        for log in result.scalars().all()
    ]
