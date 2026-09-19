from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from datetime import datetime, timedelta
from app.core.database import get_db
from app.models.models import Feedback, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("/")
async def submit_feedback(
    rating: int,
    feedback_type: str = "csat",
    title: str = None,
    content: str = None,
    job_id: UUID = None,
    customer_id: UUID = None,
    nps_score: int = None,
    db: AsyncSession = Depends(get_db)
):
    """Submit customer feedback"""
    feedback = Feedback(
        business_id=None,
        customer_id=customer_id,
        job_id=job_id,
        feedback_type=feedback_type,
        rating=rating,
        nps_score=nps_score,
        title=title,
        content=content,
    )
    db.add(feedback)
    await db.commit()
    return {"success": True}


@router.get("/stats")
async def feedback_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return {"average_rating": 0, "nps_score": 0, "total": 0, "csat": 0}

    avg_result = await db.execute(
        select(func.avg(Feedback.rating)).where(Feedback.business_id == business.id)
    )
    avg_rating = avg_result.scalar() or 0

    nps_result = await db.execute(
        select(func.avg(Feedback.nps_score)).where(
            Feedback.business_id == business.id,
            Feedback.nps_score.isnot(None),
        )
    )
    nps = nps_result.scalar() or 0

    total_result = await db.execute(
        select(func.count(Feedback.id)).where(Feedback.business_id == business.id)
    )
    total = total_result.scalar() or 0

    return {
        "average_rating": float(avg_rating),
        "nps_score": float(nps),
        "total": total,
        "csat": float(avg_rating) / 5 * 100 if avg_rating else 0,
    }


@router.get("/")
async def list_feedback(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    feedback_result = await db.execute(
        select(Feedback)
        .where(Feedback.business_id == business.id)
        .order_by(Feedback.created_at.desc())
        .limit(100)
    )
    return [
        {
            "id": str(f.id),
            "rating": f.rating,
            "nps_score": f.nps_score,
            "feedback_type": f.feedback_type,
            "title": f.title,
            "content": f.content,
            "response": f.response,
            "created_at": f.created_at.isoformat(),
        }
        for f in feedback_result.scalars().all()
    ]


@router.post("/{feedback_id}/respond")
async def respond_to_feedback(
    feedback_id: UUID,
    response: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    feedback.response = response
    feedback.responded_at = datetime.utcnow()
    await db.commit()
    return {"message": "Response added"}
