import secrets
import math
import json
from datetime import datetime, timedelta
from uuid import UUID

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import Job, Technician, User, Property, ActivityTimeline, Business
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/tracking", tags=["tracking"])
settings = get_settings()

redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

TRACKING_CODE_TTL = 86400 * 7  # 7 days
LOCATION_TTL = 300  # 5 minutes


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3959  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class LocationUpdate(BaseModel):
    latitude: float
    longitude: float
    job_id: str | None = None


class TrackingStatusResponse(BaseModel):
    status: str
    technician_name: str | None
    technician_photo_url: str | None
    estimated_arrival_minutes: int | None
    job_title: str
    scheduled_at: datetime | None


class ETAResponse(BaseModel):
    distance_miles: float
    estimated_minutes: int
    technician_location: dict
    job_location: dict


class ShareResponse(BaseModel):
    tracking_url: str
    tracking_code: str
    expires_at: datetime


class SharedTrackingResponse(BaseModel):
    job_title: str
    status: str
    technician_name: str | None
    technician_photo_url: str | None
    estimated_arrival_minutes: int | None
    distance_miles: float | None
    scheduled_at: datetime | None
    technician_location: dict | None
    job_location: dict | None
    timeline: list[dict]


async def resolve_job(db: AsyncSession, job_id: str) -> Job:
    try:
        uid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID")
    result = await db.execute(select(Job).where(Job.id == uid))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


async def get_job_coords(db: AsyncSession, job: Job) -> tuple[float, float] | None:
    if job.property_id:
        result = await db.execute(select(Property).where(Property.id == job.property_id))
        prop = result.scalar_one_or_none()
        if prop and prop.latitude and prop.longitude:
            return float(prop.latitude), float(prop.longitude)
    return None


async def get_technician_location(technician_id: UUID) -> dict | None:
    raw = await redis_client.get(f"tech:loc:{technician_id}")
    if raw:
        return json.loads(raw)
    return None


async def calc_eta(
    tech_lat: float, tech_lng: float, job_lat: float, job_lng: float
) -> tuple[float, int]:
    distance = haversine_distance(tech_lat, tech_lng, job_lat, job_lng)
    # Apply 1.3x road factor for straight-line approximation
    road_distance = distance * 1.3
    minutes = int((road_distance / 30) * 60)  # 30 mph average
    return round(road_distance, 1), max(1, minutes)


# ── Public: Job Status ────────────────────────────────────


@router.get("/{job_id}/status", response_model=TrackingStatusResponse)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await resolve_job(db, job_id)

    tech_name = None
    tech_photo = None
    estimated_minutes = None

    if job.technician_id:
        result = await db.execute(
            select(Technician).where(Technician.id == job.technician_id)
        )
        tech = result.scalar_one_or_none()
        if tech:
            user_result = await db.execute(
                select(User).where(User.id == tech.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                tech_name = user.full_name
                tech_photo = user.avatar_url

            # Calculate ETA if we have locations
            if tech.current_latitude and tech.current_longitude:
                job_coords = await get_job_coords(db, job)
                if job_coords:
                    _, estimated_minutes = await calc_eta(
                        float(tech.current_latitude),
                        float(tech.current_longitude),
                        job_coords[0],
                        job_coords[1],
                    )

    return TrackingStatusResponse(
        status=job.status.value if hasattr(job.status, "value") else job.status,
        technician_name=tech_name,
        technician_photo_url=tech_photo,
        estimated_arrival_minutes=estimated_minutes,
        job_title=job.title,
        scheduled_at=job.scheduled_at,
    )


# ── Public: Real-time ETA ─────────────────────────────────


@router.get("/{job_id}/eta", response_model=ETAResponse)
async def get_job_eta(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await resolve_job(db, job_id)

    if not job.technician_id:
        raise HTTPException(status_code=400, detail="No technician assigned")

    result = await db.execute(
        select(Technician).where(Technician.id == job.technician_id)
    )
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    # Get tech location from Redis first, fallback to DB
    tech_loc = await get_technician_location(job.technician_id)
    if tech_loc:
        tech_lat, tech_lng = tech_loc["lat"], tech_loc["lng"]
    elif tech.current_latitude and tech.current_longitude:
        tech_lat = float(tech.current_latitude)
        tech_lng = float(tech.current_longitude)
    else:
        raise HTTPException(status_code=400, detail="Technician location unavailable")

    job_coords = await get_job_coords(db, job)
    if not job_coords:
        raise HTTPException(status_code=400, detail="Job location unavailable")

    job_lat, job_lng = job_coords
    distance, minutes = await calc_eta(tech_lat, tech_lng, job_lat, job_lng)

    return ETAResponse(
        distance_miles=distance,
        estimated_minutes=minutes,
        technician_location={"lat": tech_lat, "lng": tech_lng},
        job_location={"lat": job_lat, "lng": job_lng},
    )


# ── Auth: Generate Share Link ─────────────────────────────


@router.post("/{job_id}/share", response_model=ShareResponse)
async def generate_share_link(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await resolve_job(db, job_id)

    code = secrets.token_urlsafe(16)
    expires_at = datetime.utcnow() + timedelta(days=7)

    await redis_client.setex(
        f"track:code:{code}",
        TRACKING_CODE_TTL,
        json.dumps({"job_id": str(job.id), "created_by": str(current_user.id)}),
    )

    app_url = settings.APP_URL.rstrip("/")
    return ShareResponse(
        tracking_url=f"{app_url}/track/{code}",
        tracking_code=code,
        expires_at=expires_at,
    )


# ── Public: Shared Tracking View ──────────────────────────


@router.get("/share/{tracking_code}", response_model=SharedTrackingResponse)
async def get_shared_tracking(
    tracking_code: str, db: AsyncSession = Depends(get_db)
):
    raw = await redis_client.get(f"track:code:{tracking_code}")
    if not raw:
        raise HTTPException(status_code=404, detail="Tracking link expired or invalid")

    data = json.loads(raw)
    job = await resolve_job(db, data["job_id"])

    tech_name = None
    tech_photo = None
    estimated_minutes = None
    tech_loc = None
    distance = None

    if job.technician_id:
        result = await db.execute(
            select(Technician).where(Technician.id == job.technician_id)
        )
        tech = result.scalar_one_or_none()
        if tech:
            user_result = await db.execute(
                select(User).where(User.id == tech.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                tech_name = user.full_name
                tech_photo = user.avatar_url

            tech_redis = await get_technician_location(job.technician_id)
            if tech_redis:
                tech_loc = tech_redis
            elif tech.current_latitude and tech.current_longitude:
                tech_loc = {
                    "lat": float(tech.current_latitude),
                    "lng": float(tech.current_longitude),
                }

            if tech_loc:
                job_coords = await get_job_coords(db, job)
                if job_coords:
                    distance, estimated_minutes = await calc_eta(
                        tech_loc["lat"], tech_loc["lng"],
                        job_coords[0], job_coords[1],
                    )

    job_coords = await get_job_coords(db, job)
    job_loc = {"lat": job_coords[0], "lng": job_coords[1]} if job_coords else None

    # Build timeline from activity log
    timeline_result = await db.execute(
        select(ActivityTimeline)
        .where(ActivityTimeline.job_id == job.id)
        .order_by(ActivityTimeline.created_at)
    )
    timeline = [
        {
            "action": t.action,
            "description": t.description,
            "created_at": t.created_at.isoformat(),
        }
        for t in timeline_result.scalars().all()
    ]

    return SharedTrackingResponse(
        job_title=job.title,
        status=job.status.value if hasattr(job.status, "value") else job.status,
        technician_name=tech_name,
        technician_photo_url=tech_photo,
        estimated_arrival_minutes=estimated_minutes,
        distance_miles=distance,
        scheduled_at=job.scheduled_at,
        technician_location=tech_loc,
        job_location=job_loc,
        timeline=timeline,
    )


# ── Auth: Technician Location Update ──────────────────────


@router.post("/location/update")
async def update_technician_location(
    data: LocationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify user is a technician. Resolve business with an explicit async
    # query — never touch the lazy current_user.business relationship here
    # (MissingGreenlet under async SQLAlchemy).
    biz_result = await db.execute(
        select(Business).where(Business.owner_id == current_user.id)
    )
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=403, detail="Technician profile required")
    result = await db.execute(
        select(Technician).where(
            Technician.user_id == current_user.id,
            Technician.business_id == business.id,
        )
    )
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=403, detail="Technician profile required")

    # Store in Redis with TTL
    loc_data = json.dumps({
        "lat": data.latitude,
        "lng": data.longitude,
        "updated_at": datetime.utcnow().isoformat(),
    })
    await redis_client.setex(f"tech:loc:{tech.id}", LOCATION_TTL, loc_data)

    # Also update DB for persistence
    tech.current_latitude = data.latitude
    tech.current_longitude = data.longitude
    tech.last_location_at = datetime.utcnow()
    await db.commit()

    return {"message": "Location updated"}
