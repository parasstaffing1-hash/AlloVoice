from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import InventoryItem, InventoryUsage, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("/")
async def list_inventory(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    items_result = await db.execute(
        select(InventoryItem).where(InventoryItem.business_id == business.id)
    )
    return [
        {
            "id": str(i.id),
            "name": i.name,
            "sku": i.sku,
            "quantity": i.quantity,
            "min_quantity": i.min_quantity,
            "unit_price": float(i.unit_price) if i.unit_price else None,
            "cost_price": float(i.cost_price) if i.cost_price else None,
            "unit": i.unit,
            "location_id": str(i.location_id) if i.location_id else None,
            "barcode": i.barcode,
        }
        for i in items_result.scalars().all()
    ]


@router.post("/")
async def create_inventory_item(
    name: str,
    sku: str = None,
    unit_price: float = None,
    cost_price: float = None,
    quantity: int = 0,
    min_quantity: int = 0,
    unit: str = "piece",
    barcode: str = None,
    location_id: UUID = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    item = InventoryItem(
        business_id=business.id,
        name=name,
        sku=sku,
        unit_price=unit_price,
        cost_price=cost_price,
        quantity=quantity,
        min_quantity=min_quantity,
        unit=unit,
        barcode=barcode,
        location_id=location_id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": str(item.id), "name": name}


@router.post("/{item_id}/adjust")
async def adjust_stock(
    item_id: UUID,
    quantity_change: int,
    job_id: UUID = None,
    notes: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    biz_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.id == item_id,
            InventoryItem.business_id == business.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item.quantity += quantity_change
    if item.quantity < 0:
        item.quantity = 0

    usage = InventoryUsage(
        item_id=item_id,
        job_id=job_id,
        quantity_used=abs(quantity_change),
        notes=notes or f"Stock adjusted by {quantity_change}",
    )
    db.add(usage)
    await db.commit()

    return {"new_quantity": item.quantity, "change": quantity_change}


@router.get("/low-stock")
async def low_stock_items(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    items_result = await db.execute(
        select(InventoryItem).where(
            InventoryItem.business_id == business.id,
            InventoryItem.quantity <= InventoryItem.min_quantity,
            InventoryItem.is_active == True,
        )
    )
    return [
        {
            "id": str(i.id),
            "name": i.name,
            "sku": i.sku,
            "quantity": i.quantity,
            "min_quantity": i.min_quantity,
        }
        for i in items_result.scalars().all()
    ]
