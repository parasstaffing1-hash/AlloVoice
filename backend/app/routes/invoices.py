import random
import string
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from app.core.database import get_db
from app.models.models import Invoice, InvoiceItem, Business, User, Job, Payment
from app.schemas import InvoiceCreate, InvoiceResponse, InvoiceItemResponse
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def generate_invoice_number():
    return "INV-" + "".join(random.choices(string.digits, k=6))


async def get_business_id(user: User, db: AsyncSession) -> UUID:
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business.id


@router.get("/", response_model=List[InvoiceResponse])
async def list_invoices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Invoice)
        .join(Job)
        .where(Job.business_id == business_id)
        .order_by(Invoice.created_at.desc())
    )
    invoices = result.scalars().all()
    response = []
    for inv in invoices:
        items_result = await db.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == inv.id))
        items = [InvoiceItemResponse.model_validate(i) for i in items_result.scalars().all()]
        inv_data = InvoiceResponse.model_validate(inv)
        inv_data.items = items
        response.append(inv_data)
    return response


@router.post("/", response_model=InvoiceResponse)
async def create_invoice(
    data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    subtotal = sum(item.quantity * item.unit_price for item in data.items)
    tax_amount = subtotal * (data.tax_rate / 100)
    total = subtotal + tax_amount

    invoice = Invoice(
        job_id=data.job_id,
        customer_id=data.customer_id,
        invoice_number=generate_invoice_number(),
        subtotal=subtotal,
        tax_rate=data.tax_rate,
        tax_amount=tax_amount,
        total=total,
        notes=data.notes,
        due_date=datetime.utcnow() + timedelta(days=data.due_days)
    )
    db.add(invoice)
    await db.flush()

    for i, item in enumerate(data.items):
        invoice_item = InvoiceItem(
            invoice_id=invoice.id,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total=item.quantity * item.unit_price,
            sort_order=i
        )
        db.add(invoice_item)

    job_result = await db.execute(select(Job).where(Job.id == data.job_id))
    job = job_result.scalar_one_or_none()
    if job:
        job.final_cost = total
        job.status = "invoiced"

    await db.commit()
    await db.refresh(invoice)

    items_result = await db.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id))
    items = [InvoiceItemResponse.model_validate(i) for i in items_result.scalars().all()]
    response = InvoiceResponse.model_validate(invoice)
    response.items = items
    return response


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    items_result = await db.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id))
    items = [InvoiceItemResponse.model_validate(i) for i in items_result.scalars().all()]
    response = InvoiceResponse.model_validate(invoice)
    response.items = items
    return response


@router.put("/{invoice_id}/pay")
async def mark_invoice_paid(
    invoice_id: UUID,
    amount: float = None,
    payment_method: str = "cash",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    pay_amount = amount or invoice.total
    invoice.amount_paid = pay_amount
    invoice.payment_status = "paid"
    invoice.payment_method = payment_method
    invoice.paid_at = datetime.utcnow()

    payment = Payment(
        invoice_id=invoice.id,
        amount=pay_amount,
        payment_method=payment_method
    )
    db.add(payment)

    job_result = await db.execute(select(Job).where(Job.id == invoice.job_id))
    job = job_result.scalar_one_or_none()
    if job:
        job.status = "paid"

    await db.commit()
    return {"message": "Invoice marked as paid"}
