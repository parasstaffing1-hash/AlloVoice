from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, field_validator
from app.core.database import get_db
from app.models.models import BusinessLocation, Business, User
from app.routes.auth import get_current_user
from app.services.money import CURRENCIES

router = APIRouter(prefix="/api/branches", tags=["branches"])


# ─── Business locale settings (/api/business/settings) ──────────────
# Lives in this module but mounted at /api/business via a nested router,
# so app/main.py (which already includes `branches.router`) picks it up
# without modification.

business_router = APIRouter(prefix="/api/business", tags=["business"])


class BusinessSettingsUpdate(BaseModel):
    currency: Optional[str] = None
    country_code: Optional[str] = None
    timezone: Optional[str] = None
    tax_rate: Optional[float] = None
    tax_name: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v):
        if v is None:
            return v
        code = str(v).upper()
        if code not in CURRENCIES:
            raise ValueError(f"Unsupported currency '{v}'")
        return code

    @field_validator("country_code")
    @classmethod
    def _validate_country_code(cls, v):
        if v is None:
            return v
        code = str(v).upper()
        if len(code) != 2 or not code.isalpha():
            raise ValueError("country_code must be a 2-letter uppercase code")
        return code

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v):
        if v is None:
            return v
        if not str(v).strip():
            raise ValueError("timezone must be a non-empty string")
        return str(v).strip()

    @field_validator("tax_rate")
    @classmethod
    def _validate_tax_rate(cls, v):
        if v is None:
            return v
        if float(v) < 0 or float(v) > 40:
            raise ValueError("tax_rate must be between 0 and 40")
        return float(v)


def _settings_payload(business: Business) -> dict:
    return {
        "currency": getattr(business, "currency", None) or "GBP",
        "country_code": getattr(business, "country_code", None) or "GB",
        "timezone": getattr(business, "timezone", None) or "Europe/London",
        "tax_rate": float(getattr(business, "tax_rate", None) or 20.0),
        "tax_name": getattr(business, "tax_name", None) or "VAT",
    }


@business_router.get("/settings")
async def get_business_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return _settings_payload(business)


@business_router.put("/settings")
async def update_business_settings(
    data: BusinessSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(business, key, value)
    await db.commit()
    await db.refresh(business)
    return _settings_payload(business)


router.include_router(business_router)


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
