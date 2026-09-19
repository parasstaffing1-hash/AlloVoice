from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import FleetVehicle, FleetTrip, Technician, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


@router.get("/vehicles")
async def list_vehicles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    vehicles_result = await db.execute(
        select(FleetVehicle).where(FleetVehicle.business_id == business.id)
    )
    return [
        {
            "id": str(v.id),
            "registration": v.registration,
            "make": v.make,
            "model": v.model,
            "year": v.year,
            "assigned_technician_id": str(v.assigned_technician_id) if v.assigned_technician_id else None,
        }
        for v in vehicles_result.scalars().all()
    ]


@router.post("/vehicles")
async def create_vehicle(
    registration: str,
    make: str = None,
    model: str = None,
    year: int = None,
    assigned_technician_id: UUID = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    vehicle = FleetVehicle(
        business_id=business.id,
        registration=registration,
        make=make,
        model=model,
        year=year,
        assigned_technician_id=assigned_technician_id,
    )
    db.add(vehicle)
    await db.commit()
    await db.refresh(vehicle)
    return {"id": str(vehicle.id), "registration": registration}


@router.post("/location/update")
async def update_location(
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
        tech.current_latitude = latitude
        tech.current_longitude = longitude
        tech.last_location_at = datetime.utcnow()
        await db.commit()
    return {"success": True}


@router.get("/positions")
async def get_positions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all technician positions"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    techs_result = await db.execute(
        select(Technician).where(
            Technician.business_id == business.id,
            Technician.current_latitude.isnot(None),
        )
    )
    return [
        {
            "technician_id": str(t.id),
            "latitude": float(t.current_latitude),
            "longitude": float(t.current_longitude),
            "last_updated": t.last_location_at.isoformat() if t.last_location_at else None,
        }
        for t in techs_result.scalars().all()
    ]


@router.get("/trips/{vehicle_id}")
async def list_trips(
    vehicle_id: UUID,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    trips_result = await db.execute(
        select(FleetTrip)
        .where(FleetTrip.vehicle_id == vehicle_id)
        .order_by(FleetTrip.started_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": str(t.id),
            "distance_km": float(t.distance_km) if t.distance_km else None,
            "duration_minutes": t.duration_minutes,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "ended_at": t.ended_at.isoformat() if t.ended_at else None,
        }
        for t in trips_result.scalars().all()
    ]
