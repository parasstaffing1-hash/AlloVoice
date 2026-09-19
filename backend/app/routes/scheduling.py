import math
from datetime import datetime, timedelta, date
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import (
    Job, User, Business, Technician, Customer, Property, ActivityTimeline, JobStatus,
)
from app.routes.auth import get_current_user
from app.services.calendar_invite import build_job_ics

router = APIRouter(prefix="/api/scheduling", tags=["scheduling"])

POSTCODES_BASE_URL = "https://api.postcodes.io"


# ── Pydantic schemas ──────────────────────────────────────────


class OptimizeRequest(BaseModel):
    job_id: UUID
    technician_ids: List[UUID]


class Assignment(BaseModel):
    technician_id: UUID
    technician_name: str
    estimated_travel_minutes: int
    departure_time: datetime


class OptimizeResponse(BaseModel):
    assignments: List[Assignment]


class AutoAssignResponse(BaseModel):
    assigned: List[dict]
    unassigned: List[UUID]


class AvailabilitySlot(BaseModel):
    date: date
    available_hours: float
    booked_hours: float
    utilization_pct: float


class AvailabilityResponse(BaseModel):
    slots: List[AvailabilitySlot]


class RescheduleRequest(BaseModel):
    job_id: UUID
    new_scheduled_at: datetime


class RescheduleResponse(BaseModel):
    message: str
    rescheduled_job: UUID
    dependent_jobs_updated: List[UUID]


# ── Helpers ───────────────────────────────────────────────────


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lng points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def postcode_coords(postcode: str) -> Optional[tuple[float, float]]:
    """Return (lat, lng) for a UK postcode via Postcodes.io, or None."""
    clean = postcode.replace(" ", "").strip()
    if not clean:
        return None
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(f"{POSTCODES_BASE_URL}/postcodes/{clean}")
        if resp.status_code == 200:
            r = resp.json().get("result", {})
            return (r.get("latitude"), r.get("longitude"))
    return None


async def get_business_id(user: User, db: AsyncSession) -> UUID:
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business.id


def estimate_travel_minutes(dist_km: float) -> int:
    """Rough travel estimate: 30 km/h average in mixed traffic."""
    if dist_km <= 0:
        return 0
    return max(5, round(dist_km / 30 * 60))


# ── Endpoints ─────────────────────────────────────────────────


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_assignment(
    body: OptimizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Find the optimal technician for a single job based on skills, proximity, and workload."""
    business_id = await get_business_id(current_user, db)

    # Fetch the job
    result = await db.execute(
        select(Job).where(Job.id == body.job_id, Job.business_id == business_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Job location coords
    job_lat, job_lng = None, None
    if job.property_id:
        prop = await db.get(Property, job.property_id)
        if prop:
            job_lat, job_lng = float(prop.latitude) if prop.latitude else None, float(prop.longitude) if prop.longitude else None
            if job_lat is None and prop.zip_code:
                coords = await postcode_coords(prop.zip_code)
                if coords:
                    job_lat, job_lng = coords

    if job_lat is None:
        raise HTTPException(status_code=400, detail="Job has no resolvable location")

    # Fetch requested technicians
    result = await db.execute(
        select(Technician).where(
            Technician.id.in_(body.technician_ids),
            Technician.business_id == business_id,
            Technician.is_available == True,
        )
    )
    technicians = result.scalars().all()
    if not technicians:
        raise HTTPException(status_code=400, detail="No available technicians found")

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    scored: list[dict] = []
    for tech in technicians:
        # Travel distance
        tech_lat = float(tech.current_latitude) if tech.current_latitude else None
        tech_lng = float(tech.current_longitude) if tech.current_longitude else None
        if tech_lat is None:
            dist_km = 999.0
        else:
            dist_km = haversine_km(tech_lat, tech_lng, job_lat, job_lng)

        travel_min = estimate_travel_minutes(dist_km)

        # Workload today
        workload_result = await db.execute(
            select(func.count(Job.id)).where(
                Job.technician_id == tech.id,
                Job.scheduled_at >= today_start,
                Job.scheduled_at < today_end,
                Job.status.notin_([JobStatus.CANCELLED.value, JobStatus.COMPLETED.value]),
            )
        )
        today_jobs = workload_result.scalar() or 0

        # Skill match (simple substring check on comma-separated skills string)
        tech_skills = (tech.skills or "").lower()
        # For now we treat all skills as matching unless we add job-skill requirements later
        skill_match = 1.0

        # Composite score: lower is better
        score = dist_km * 2 + travel_min * 0.5 + today_jobs * 15 + (0 if skill_match else 100)

        # Departure time: now + existing workload buffer
        departure = datetime.utcnow() + timedelta(minutes=today_jobs * 15)

        user_obj = await db.get(User, tech.user_id)
        scored.append(
            {
                "technician_id": tech.id,
                "technician_name": user_obj.full_name if user_obj else "Unknown",
                "estimated_travel_minutes": travel_min,
                "departure_time": departure,
                "score": score,
            }
        )

    scored.sort(key=lambda x: x["score"])
    return OptimizeResponse(
        assignments=[
            Assignment(
                technician_id=s["technician_id"],
                technician_name=s["technician_name"],
                estimated_travel_minutes=s["estimated_travel_minutes"],
                departure_time=s["departure_time"],
            )
            for s in scored
        ]
    )


@router.post("/auto-assign", response_model=AutoAssignResponse)
async def auto_assign_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Auto-assign all unassigned scheduled jobs for today using greedy nearest-available."""
    business_id = await get_business_id(current_user, db)

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Unassigned jobs scheduled today (or any future date with no tech)
    result = await db.execute(
        select(Job).where(
            Job.business_id == business_id,
            Job.technician_id.is_(None),
            Job.scheduled_at >= today_start,
            Job.scheduled_at < today_end,
            Job.status.in_([JobStatus.SCHEDULED.value, JobStatus.QUOTE_APPROVED.value]),
        )
    )
    jobs = result.scalars().all()

    # Available technicians
    result = await db.execute(
        select(Technician).where(
            Technician.business_id == business_id,
            Technician.is_available == True,
        )
    )
    technicians = list(result.scalars().all())

    # Pre-fetch tech user names and current jobs count
    tech_map: dict[UUID, dict] = {}
    for tech in technicians:
        user_obj = await db.get(User, tech.user_id)
        tech_lat = float(tech.current_latitude) if tech.current_latitude else None
        tech_lng = float(tech.current_longitude) if tech.current_longitude else None
        workload_r = await db.execute(
            select(func.count(Job.id)).where(
                Job.technician_id == tech.id,
                Job.scheduled_at >= today_start,
                Job.scheduled_at < today_end,
                Job.status.notin_([JobStatus.CANCELLED.value, JobStatus.COMPLETED.value]),
            )
        )
        tech_map[tech.id] = {
            "tech": tech,
            "name": user_obj.full_name if user_obj else "Unknown",
            "lat": tech_lat,
            "lng": tech_lng,
            "today_jobs": workload_r.scalar() or 0,
        }

    assigned: list[dict] = []
    unassigned: list[UUID] = []

    for job in jobs:
        # Resolve job location
        job_lat, job_lng = None, None
        if job.property_id:
            prop = await db.get(Property, job.property_id)
            if prop:
                job_lat = float(prop.latitude) if prop.latitude else None
                job_lng = float(prop.longitude) if prop.longitude else None
                if job_lat is None and prop.zip_code:
                    coords = await postcode_coords(prop.zip_code)
                    if coords:
                        job_lat, job_lng = coords

        if job_lat is None:
            unassigned.append(job.id)
            continue

        best_tech_id = None
        best_score = float("inf")

        for tid, info in tech_map.items():
            if info["lat"] is None:
                continue
            dist = haversine_km(info["lat"], info["lng"], job_lat, job_lng)
            travel = estimate_travel_minutes(dist)
            score = dist * 2 + travel * 0.5 + info["today_jobs"] * 15
            if score < best_score:
                best_score = score
                best_tech_id = tid

        if best_tech_id is None:
            unassigned.append(job.id)
            continue

        # Assign
        job.technician_id = best_tech_id
        job.status = JobStatus.SCHEDULED
        db.add(
            ActivityTimeline(
                job_id=job.id,
                user_id=current_user.id,
                action="auto_assigned",
                description=f"Auto-assigned to {tech_map[best_tech_id]['name']}",
            )
        )
        assigned.append({"job_id": str(job.id), "technician_id": str(best_tech_id)})
        tech_map[best_tech_id]["today_jobs"] += 1

    await db.commit()
    return AutoAssignResponse(assigned=assigned, unassigned=unassigned)


@router.get("/availability", response_model=AvailabilityResponse)
async def get_availability(
    start_date: date = Query(...),
    end_date: date = Query(...),
    technician_id: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get technician availability slots for a date range."""
    business_id = await get_business_id(current_user, db)

    # Determine which technicians to include
    tech_query = select(Technician).where(
        Technician.business_id == business_id,
        Technician.is_available == True,
    )
    if technician_id:
        tech_query = tech_query.where(Technician.id == technician_id)

    result = await db.execute(tech_query)
    technicians = result.scalars().all()
    if not technicians:
        return AvailabilityResponse(slots=[])

    tech_ids = [t.id for t in technicians]
    WORK_HOURS_PER_DAY = 8.0

    current = start_date
    slots: list[AvailabilitySlot] = []

    while current <= end_date:
        day_start = datetime.combine(current, datetime.min.time())
        day_end = day_start + timedelta(days=1)

        # Count booked hours for all technicians on this day
        booked_result = await db.execute(
            select(func.count(Job.id)).where(
                Job.technician_id.in_(tech_ids),
                Job.business_id == business_id,
                Job.scheduled_at >= day_start,
                Job.scheduled_at < day_end,
                Job.status.notin_([JobStatus.CANCELLED.value]),
            )
        )
        booked_count = booked_result.scalar() or 0
        booked_hours = booked_count * 1.5  # assume 1.5 h per job average

        total_available = WORK_HOURS_PER_DAY * len(technicians)
        available_hours = max(0, total_available - booked_hours)
        utilization = (booked_hours / total_available * 100) if total_available > 0 else 0

        slots.append(
            AvailabilitySlot(
                date=current,
                available_hours=round(available_hours, 1),
                booked_hours=round(booked_hours, 1),
                utilization_pct=round(utilization, 1),
            )
        )
        current += timedelta(days=1)

    return AvailabilityResponse(slots=slots)


@router.post("/reschedule", response_model=RescheduleResponse)
async def reschedule_job(
    body: RescheduleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reschedule a job and update any dependent (contract-linked) future jobs."""
    business_id = await get_business_id(current_user, db)

    result = await db.execute(
        select(Job).where(Job.id == body.job_id, Job.business_id == business_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    old_time = job.scheduled_at
    job.scheduled_at = body.new_scheduled_at

    db.add(
        ActivityTimeline(
            job_id=job.id,
            user_id=current_user.id,
            action="rescheduled",
            description=f"Rescheduled from {old_time} to {body.new_scheduled_at}",
        )
    )

    # Update dependent jobs: if this job is linked to a contract and has a
    # follow-up job with the same contract scheduled right after the old time,
    # shift it forward by the same delta.
    dependent_ids: list[UUID] = []
    if job.contract_id and old_time:
        delta = body.new_scheduled_at - old_time
        dependent_result = await db.execute(
            select(Job).where(
                Job.contract_id == job.contract_id,
                Job.id != job.id,
                Job.scheduled_at > old_time,
                Job.scheduled_at <= old_time + timedelta(days=7),
                Job.status.in_([JobStatus.SCHEDULED.value]),
            )
        )
        for dep_job in dependent_result.scalars().all():
            dep_job.scheduled_at = dep_job.scheduled_at + delta
            dependent_ids.append(dep_job.id)
            db.add(
                ActivityTimeline(
                    job_id=dep_job.id,
                    user_id=current_user.id,
                    action="dependent_reschedule",
                    description=f"Shifted {delta} due to parent job reschedule",
                )
            )

    await db.commit()
    return RescheduleResponse(
        message="Job rescheduled successfully",
        rescheduled_job=job.id,
        dependent_jobs_updated=dependent_ids,
    )


@router.get("/invite/{job_id}")
async def get_job_invite(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a .ics calendar invite for a job (1-hour duration default)."""
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.business_id == business_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    location = ""
    if job.property_id:
        prop = await db.get(Property, job.property_id)
        if prop:
            parts = [
                getattr(prop, "address_line1", None),
                getattr(prop, "city", None),
                getattr(prop, "zip_code", None),
            ]
            location = ", ".join([p for p in parts if p])

    start = job.scheduled_at or datetime.utcnow()
    end = start + timedelta(hours=1)
    organizer_email = getattr(current_user, "email", "") or ""

    ics_bytes = build_job_ics(
        summary=job.title or "Job",
        description=job.description or "",
        location=location,
        start_iso=start.isoformat(),
        end_iso=end.isoformat(),
        organizer_email=organizer_email,
    )
    return Response(
        content=ics_bytes,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="job-{job_id}.ics"'},
    )
