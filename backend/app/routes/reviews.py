from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from app.core.database import get_db
from app.models.models import Review, Job, Business, User
from app.schemas import ReviewCreate, ReviewResponse
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("/", response_model=List[ReviewResponse])
async def list_reviews(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []
    result = await db.execute(
        select(Review)
        .where(Review.business_id == business.id)
        .order_by(Review.created_at.desc())
    )
    return [ReviewResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/", response_model=ReviewResponse)
async def create_review(
    data: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    # Job must belong to the caller's business (no cross-tenant reviews).
    job_result = await db.execute(
        select(Job).where(Job.id == data.job_id, Job.business_id == business.id)
    )
    if not job_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")
    review = Review(
        job_id=data.job_id,
        customer_id=data.customer_id if hasattr(data, 'customer_id') else None,
        business_id=business.id,
        rating=data.rating,
        title=data.title,
        content=data.content
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return ReviewResponse.model_validate(review)
