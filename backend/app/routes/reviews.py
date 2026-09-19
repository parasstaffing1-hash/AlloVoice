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
    result = await db.execute(
        select(Review)
        .join(Job)
        .where(Job.business_id.in_(
            select(Business.id).where(Business.owner_id == current_user.id)
        ))
        .order_by(Review.created_at.desc())
    )
    return [ReviewResponse.model_validate(r) for r in result.scalars().all()]


@router.post("/", response_model=ReviewResponse)
async def create_review(
    data: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    review = Review(
        job_id=data.job_id,
        customer_id=data.customer_id if hasattr(data, 'customer_id') else None,
        rating=data.rating,
        title=data.title,
        content=data.content
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return ReviewResponse.model_validate(review)
