from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import Job, Business, User, Customer, Technician, JobPhoto, ActivityTimeline
from app.schemas import JobCreate, JobResponse
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


async def get_business_id(user: User, db: AsyncSession) -> UUID:
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business.id


@router.get("/", response_model=List[JobResponse])
async def list_jobs(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    query = select(Job).where(Job.business_id == business_id)
    if status:
        query = query.where(Job.status == status)
    query = query.order_by(Job.created_at.desc())
    result = await db.execute(query)
    return [JobResponse.model_validate(j) for j in result.scalars().all()]


@router.post("/", response_model=JobResponse)
async def create_job(
    data: JobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    job = Job(business_id=business_id, **data.model_dump())
    db.add(job)
    await db.flush()  # populate job.id (Python-side uuid default fires on flush)

    timeline = ActivityTimeline(
        job_id=job.id,
        user_id=current_user.id,
        action="job_created",
        description=f"Job '{data.title}' created"
    )
    db.add(timeline)
    await db.commit()
    await db.refresh(job)
    return JobResponse.model_validate(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.business_id == business_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@router.put("/{job_id}/status")
async def update_job_status(
    job_id: UUID,
    status: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.business_id == business_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = status
    if status == "in_progress":
        job.started_at = datetime.utcnow()
    elif status == "completed":
        job.completed_at = datetime.utcnow()

    timeline = ActivityTimeline(
        job_id=job.id,
        user_id=current_user.id,
        action="status_changed",
        description=f"Status changed to {status}"
    )
    db.add(timeline)
    await db.commit()

    if status == "completed":
        try:
            from app.services.analytics import capture

            try:
                job_value = float(job.final_cost or job.estimated_cost or 0)
            except Exception:
                job_value = 0.0
            capture(
                "job_completed",
                distinct_id=str(current_user.id),
                properties={"job_id": str(job.id), "value": job_value},
            )
        except Exception:
            pass

    return {"message": "Status updated"}


@router.put("/{job_id}/assign")
async def assign_technician(
    job_id: UUID,
    technician_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.business_id == business_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await db.execute(
        select(Technician).where(Technician.id == technician_id, Technician.business_id == business_id)
    )
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    job.technician_id = technician_id
    timeline = ActivityTimeline(
        job_id=job.id,
        user_id=current_user.id,
        action="technician_assigned",
        description=f"Technician assigned"
    )
    db.add(timeline)
    await db.commit()
    return {"message": "Technician assigned"}


@router.post("/{job_id}/photos")
async def upload_photo(
    job_id: UUID,
    url: str,
    photo_type: str = "before",
    caption: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    photo = JobPhoto(
        job_id=job_id,
        url=url,
        photo_type=photo_type,
        caption=caption
    )
    db.add(photo)
    await db.commit()
    return {"message": "Photo uploaded", "id": str(photo.id)}


@router.put("/{job_id}/ai-summary")
async def update_ai_summary(
    job_id: UUID,
    summary: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.business_id == business_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.ai_summary = summary
    await db.commit()
    return {"message": "AI summary updated"}
