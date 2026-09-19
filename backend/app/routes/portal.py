from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import Customer, Quote, Invoice, Job, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/portal", tags=["portal"])
settings = get_settings()


@router.post("/auth")
async def portal_auth(
    email: str,
    token: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate customer via magic link or token"""
    if token:
        result = await db.execute(
            select(Customer).where(
                Customer.portal_token == token,
                Customer.portal_enabled == True,
                Customer.is_active == True,
            )
        )
        customer = result.scalar_one_or_none()
        if customer:
            return {
                "authenticated": True,
                "customer_id": str(customer.id),
                "customer_name": customer.full_name,
            }

    if email:
        result = await db.execute(
            select(Customer).where(
                Customer.email == email,
                Customer.portal_enabled == True,
                Customer.is_active == True,
            )
        )
        customer = result.scalar_one_or_none()
        if customer:
            # In production, send magic link email
            return {"magic_link_sent": True, "email": email}

    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.get("/quotes")
async def portal_quotes(
    customer_id: UUID,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Get quotes for portal customer"""
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.portal_token == token,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=401, detail="Unauthorized")

    quotes_result = await db.execute(
        select(Quote).where(Quote.customer_id == customer_id).order_by(Quote.created_at.desc())
    )
    return [
        {
            "id": str(q.id),
            "quote_number": q.quote_number,
            "title": q.title,
            "total": float(q.total),
            "is_accepted": q.is_accepted,
            "valid_until": q.valid_until.isoformat() if q.valid_until else None,
            "created_at": q.created_at.isoformat(),
        }
        for q in quotes_result.scalars().all()
    ]


@router.get("/invoices")
async def portal_invoices(
    customer_id: UUID,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Get invoices for portal customer"""
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.portal_token == token,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=401, detail="Unauthorized")

    inv_result = await db.execute(
        select(Invoice).where(Invoice.customer_id == customer_id).order_by(Invoice.created_at.desc())
    )
    return [
        {
            "id": str(i.id),
            "invoice_number": i.invoice_number,
            "total": float(i.total),
            "amount_paid": float(i.amount_paid),
            "payment_status": i.payment_status.value if hasattr(i.payment_status, 'value') else i.payment_status,
            "due_date": i.due_date.isoformat() if i.due_date else None,
            "created_at": i.created_at.isoformat(),
        }
        for i in inv_result.scalars().all()
    ]


@router.get("/jobs")
async def portal_jobs(
    customer_id: UUID,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Get jobs for portal customer"""
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.portal_token == token,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=401, detail="Unauthorized")

    jobs_result = await db.execute(
        select(Job).where(Job.customer_id == customer_id).order_by(Job.created_at.desc())
    )
    return [
        {
            "id": str(j.id),
            "title": j.title,
            "status": j.status.value if hasattr(j.status, 'value') else j.status,
            "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "created_at": j.created_at.isoformat(),
        }
        for j in jobs_result.scalars().all()
    ]


@router.post("/quotes/{quote_id}/accept")
async def portal_accept_quote(
    quote_id: UUID,
    customer_id: UUID,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Accept a quote from the portal"""
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.portal_token == token,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=401, detail="Unauthorized")

    quote_result = await db.execute(
        select(Quote).where(Quote.id == quote_id, Quote.customer_id == customer_id)
    )
    quote = quote_result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote.is_accepted = True
    quote.accepted_at = datetime.utcnow()
    await db.commit()

    return {"message": "Quote accepted"}
