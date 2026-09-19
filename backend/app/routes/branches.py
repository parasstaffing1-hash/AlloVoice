from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.core.database import get_db
from app.models.models import BusinessLocation, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/branches", tags=["branches"])


@router.get("/")
async def list_locations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    locs_result = await db.execute(
        select(BusinessLocation).where(BusinessLocation.business_id == business.id)
    )
    return [
        {
            "id": str(l.id),
            "name": l.name,
            "address_line1": l.address_line1,
            "city": l.city,
            "state": l.state,
            "zip_code": l.zip_code,
            "latitude": float(l.latitude) if l.latitude else None,
            "longitude": float(l.longitude) if l.longitude else None,
            "is_default": l.is_default,
        }
        for l in locs_result.scalars().all()
    ]


@router.post("/")
async def create_location(
    name: str,
    address_line1: str = None,
    city: str = None,
    state: str = None,
    zip_code: str = None,
    latitude: float = None,
    longitude: float = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    existing = await db.execute(
        select(BusinessLocation).where(BusinessLocation.business_id == business.id)
    )
    is_first = len(existing.scalars().all()) == 0

    location = BusinessLocation(
        business_id=business.id,
        name=name,
        address_line1=address_line1,
        city=city,
        state=state,
        zip_code=zip_code,
        latitude=latitude,
        longitude=longitude,
        is_default=is_first,
    )
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return {"id": str(location.id), "name": name}


@router.put("/{location_id}")
async def update_location(
    location_id: UUID,
    name: str = None,
    address_line1: str = None,
    city: str = None,
    state: str = None,
    zip_code: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    biz_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    result = await db.execute(
        select(BusinessLocation).where(
            BusinessLocation.id == location_id,
            BusinessLocation.business_id == business.id,
        )
    )
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    if name: location.name = name
    if address_line1: location.address_line1 = address_line1
    if city: location.city = city
    if state: location.state = state
    if zip_code: location.zip_code = zip_code
    await db.commit()
    return {"message": "Location updated"}


@router.delete("/{location_id}")
async def delete_location(
    location_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    biz_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    result = await db.execute(
        select(BusinessLocation).where(
            BusinessLocation.id == location_id,
            BusinessLocation.business_id == business.id,
        )
    )
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    location.is_active = False
    await db.commit()
    return {"message": "Location deleted"}
