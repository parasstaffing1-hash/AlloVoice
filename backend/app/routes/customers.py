from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from app.core.database import get_db
from app.models.models import Customer, Property, Business, User
from app.schemas import CustomerCreate, CustomerResponse, PropertyCreate, PropertyResponse
from app.routes.auth import get_current_user
from app.services.phone import normalize_uk_phone

router = APIRouter(prefix="/api/customers", tags=["customers"])


async def get_business_id(user: User, db: AsyncSession) -> UUID:
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business.id


@router.get("/", response_model=List[CustomerResponse])
async def list_customers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Customer).where(Customer.business_id == business_id).order_by(Customer.created_at.desc())
    )
    return [CustomerResponse.model_validate(c) for c in result.scalars().all()]


@router.post("/", response_model=CustomerResponse)
async def create_customer(
    data: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    payload = data.model_dump()
    if payload.get("phone"):
        try:
            payload["phone"] = normalize_uk_phone(payload["phone"])
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid UK phone number")
    customer = Customer(business_id=business_id, **payload)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return CustomerResponse.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.business_id == business_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerResponse.model_validate(customer)


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    data: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.business_id == business_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    updates = data.model_dump(exclude_unset=True)
    if "phone" in updates and updates["phone"]:
        try:
            updates["phone"] = normalize_uk_phone(updates["phone"])
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid UK phone number")
    for key, value in updates.items():
        setattr(customer, key, value)
    await db.commit()
    await db.refresh(customer)
    return CustomerResponse.model_validate(customer)


@router.delete("/{customer_id}")
async def delete_customer(
    customer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.business_id == business_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.is_active = False
    await db.commit()
    return {"message": "Customer deleted"}


@router.get("/{customer_id}/properties", response_model=List[PropertyResponse])
async def list_properties(
    customer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Property).where(Property.customer_id == customer_id).order_by(Property.created_at.desc())
    )
    return [PropertyResponse.model_validate(p) for p in result.scalars().all()]


@router.post("/{customer_id}/properties", response_model=PropertyResponse)
async def create_property(
    customer_id: UUID,
    data: PropertyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    property = Property(customer_id=customer_id, **data.model_dump())
    db.add(property)
    await db.commit()
    await db.refresh(property)
    return PropertyResponse.model_validate(property)
