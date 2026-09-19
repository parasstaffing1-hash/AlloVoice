from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.core.database import get_db
from app.models.models import Customer, Job, Invoice, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/")
async def global_search(
    q: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Full-text search across all entities"""
    if not q or len(q) < 2:
        return {"results": []}

    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return {"results": []}

    results = []

    # Search customers
    cust_result = await db.execute(
        select(Customer).where(
            Customer.business_id == business.id,
            or_(
                Customer.full_name.ilike(f"%{q}%"),
                Customer.email.ilike(f"%{q}%"),
                Customer.phone.ilike(f"%{q}%"),
                Customer.company.ilike(f"%{q}%"),
            )
        ).limit(10)
    )
    for c in cust_result.scalars().all():
        results.append({
            "type": "customer",
            "id": str(c.id),
            "title": c.full_name,
            "subtitle": c.company or c.phone,
        })

    # Search jobs
    jobs_result = await db.execute(
        select(Job).where(
            Job.business_id == business.id,
            or_(
                Job.title.ilike(f"%{q}%"),
                Job.description.ilike(f"%{q}%"),
                Job.notes.ilike(f"%{q}%"),
            )
        ).limit(10)
    )
    for j in jobs_result.scalars().all():
        results.append({
            "type": "job",
            "id": str(j.id),
            "title": j.title,
            "subtitle": j.status.value if hasattr(j.status, 'value') else j.status,
        })

    # Search invoices
    inv_result = await db.execute(
        select(Invoice).where(
            Invoice.invoice_number.ilike(f"%{q}%"),
        ).limit(5)
    )
    for i in inv_result.scalars().all():
        results.append({
            "type": "invoice",
            "id": str(i.id),
            "title": i.invoice_number,
            "subtitle": f"£{float(i.total):.2f}",
        })

    return {"results": results, "total": len(results)}
