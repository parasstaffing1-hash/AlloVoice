from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import Job, Business, User, Technician
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/realtime", tags=["realtime"])


@router.get("/dispatch/board")
async def get_dispatch_board(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get real-time dispatch board data"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return {"jobs": [], "technicians": []}

    # Get active jobs
    jobs_result = await db.execute(
        select(Job).where(
            Job.business_id == business.id,
            Job.status.in_(["scheduled", "in_progress", "quote_approved"])
        ).order_by(Job.scheduled_at.asc())
    )
    jobs = jobs_result.scalars().all()

    # Get technicians
    tech_result = await db.execute(
        select(Technician).where(Technician.business_id == business.id)
    )
    techs = tech_result.scalars().all()

    return {
        "jobs": [
            {
                "id": str(j.id),
                "title": j.title,
                "status": j.status,
                "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
                "technician_id": str(j.technician_id) if j.technician_id else None,
            }
            for j in jobs
        ],
        "technicians": [
            {
                "id": str(t.id),
                "user_id": str(t.user_id),
                "skills": t.skills,
                "is_available": t.is_available,
            }
            for t in techs
        ],
    }


@router.post("/location/update")
async def update_technician_location(
    latitude: float,
    longitude: float,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update technician GPS location"""
    result = await db.execute(
        select(Technician).where(Technician.user_id == current_user.id)
    )
    tech = result.scalar_one_or_none()
    if tech:
        # In production, store in Redis for real-time access
        return {"message": "Location updated", "lat": latitude, "lng": longitude}
    return {"message": "No technician profile found"}
