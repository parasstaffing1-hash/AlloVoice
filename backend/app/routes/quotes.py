import random
import string
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from app.core.database import get_db
from app.models.models import Quote, QuoteItem, Business, User, Job
from app.schemas import QuoteCreate, QuoteResponse, QuoteItemResponse
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


def generate_quote_number():
    return "Q-" + "".join(random.choices(string.digits, k=6))


async def get_business_id(user: User, db: AsyncSession) -> UUID:
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business.id


@router.get("/", response_model=List[QuoteResponse])
async def list_quotes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Quote)
        .where(Quote.business_id == business_id)
        .order_by(Quote.created_at.desc())
    )
    quotes = result.scalars().all()
    response = []
    for q in quotes:
        items_result = await db.execute(select(QuoteItem).where(QuoteItem.quote_id == q.id))
        items = [QuoteItemResponse.model_validate(i) for i in items_result.scalars().all()]
        q.__dict__["items"] = items
        quote_data = QuoteResponse.model_validate(q)
        quote_data.items = items
        response.append(quote_data)
    return response


@router.post("/", response_model=QuoteResponse)
async def create_quote(
    data: QuoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    job_check = await db.execute(
        select(Job).where(Job.id == data.job_id, Job.business_id == business_id)
    )
    if not job_check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")
    subtotal = sum(item.quantity * item.unit_price for item in data.items)
    tax_amount = subtotal * (data.tax_rate / 100)
    total = subtotal + tax_amount

    quote = Quote(
        job_id=data.job_id,
        customer_id=data.customer_id,
        business_id=business_id,
        quote_number=generate_quote_number(),
        title=data.title,
        subtotal=subtotal,
        tax_rate=data.tax_rate,
        tax_amount=tax_amount,
        total=total,
        notes=data.notes,
        valid_until=datetime.utcnow() + timedelta(days=data.valid_days)
    )
    db.add(quote)
    await db.flush()

    for i, item in enumerate(data.items):
        quote_item = QuoteItem(
            quote_id=quote.id,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total=item.quantity * item.unit_price,
            sort_order=i
        )
        db.add(quote_item)

    job_result = await db.execute(select(Job).where(Job.id == data.job_id))
    job = job_result.scalar_one_or_none()
    if job:
        job.estimated_cost = total
        job.status = "quote_sent"

    await db.commit()
    await db.refresh(quote)

    items_result = await db.execute(select(QuoteItem).where(QuoteItem.quote_id == quote.id))
    items = [QuoteItemResponse.model_validate(i) for i in items_result.scalars().all()]
    # Pre-seed relationship: validating QuoteResponse reads .items, which
    # would lazy-load (MissingGreenlet) under async SQLAlchemy.
    quote.__dict__["items"] = items
    response = QuoteResponse.model_validate(quote)
    response.items = items
    return response


@router.get("/{quote_id}", response_model=QuoteResponse)
async def get_quote(
    quote_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id, Quote.business_id == business_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    items_result = await db.execute(select(QuoteItem).where(QuoteItem.quote_id == quote.id))
    items = [QuoteItemResponse.model_validate(i) for i in items_result.scalars().all()]
    quote.__dict__["items"] = items
    response = QuoteResponse.model_validate(quote)
    response.items = items
    return response


@router.put("/{quote_id}/accept")
async def accept_quote(
    quote_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id, Quote.business_id == business_id)
    )
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote.is_accepted = True
    quote.accepted_at = datetime.utcnow()

    job_result = await db.execute(select(Job).where(Job.id == quote.job_id))
    job = job_result.scalar_one_or_none()
    if job:
        job.status = "quote_approved"

    await db.commit()
    return {"message": "Quote accepted"}
