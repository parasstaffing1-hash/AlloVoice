from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import AnalyticsEvent, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("/event")
async def track_event(
    event: str,
    properties: dict = None,
    session_id: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Track an analytics event"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()

    analytics_event = AnalyticsEvent(
        business_id=business.id if business else None,
        event=event,
        properties=properties,
        user_id=current_user.id,
        session_id=session_id,
    )
    db.add(analytics_event)
    await db.commit()
    return {"success": True}


@router.get("/events")
async def list_events(
    event: str = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    query = select(AnalyticsEvent).where(AnalyticsEvent.business_id == business.id)
    if event:
        query = query.where(AnalyticsEvent.event == event)

    events_result = await db.execute(
        query.order_by(AnalyticsEvent.created_at.desc()).limit(limit)
    )
    return [
        {
            "id": str(e.id),
            "event": e.event,
            "properties": e.properties,
            "created_at": e.created_at.isoformat(),
        }
        for e in events_result.scalars().all()
    ]


@router.get("/summary")
async def analytics_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Analytics summary"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return {"total_events": 0, "unique_sessions": 0}

    from sqlalchemy import func
    total = await db.execute(
        select(func.count(AnalyticsEvent.id)).where(AnalyticsEvent.business_id == business.id)
    )
    sessions = await db.execute(
        select(func.count(func.distinct(AnalyticsEvent.session_id)))
        .where(AnalyticsEvent.business_id == business.id)
    )

    return {
        "total_events": total.scalar() or 0,
        "unique_sessions": sessions.scalar() or 0,
    }
