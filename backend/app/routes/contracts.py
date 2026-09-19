from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import Contract, Job, Business, Customer, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


@router.post("/")
async def create_contract(
    customer_id: UUID,
    title: str,
    frequency: str,
    monthly_price: float,
    start_date: str,
    end_date: str = None,
    sla_response_hours: int = 24,
    sla_resolution_hours: int = 48,
    description: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a maintenance contract"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Generate RRULE based on frequency
    rrules = {
        "weekly": "FREQ=WEEKLY",
        "monthly": "FREQ=MONTHLY",
        "quarterly": "FREQ=MONTHLY;INTERVAL=3",
        "biannual": "FREQ=MONTHLY;INTERVAL=6",
        "annual": "FREQ=YEARLY",
    }

    contract = Contract(
        business_id=business.id,
        customer_id=customer_id,
        title=title,
        description=description,
        frequency=frequency,
        rrule=rrules.get(frequency, "FREQ=MONTHLY"),
        monthly_price=monthly_price,
        start_date=datetime.fromisoformat(start_date),
        end_date=datetime.fromisoformat(end_date) if end_date else None,
        sla_response_hours=sla_response_hours,
        sla_resolution_hours=sla_resolution_hours,
        status="active",
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)

    return {"id": str(contract.id), "title": title, "frequency": frequency}


@router.get("/")
async def list_contracts(
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all contracts"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    query = select(Contract).where(Contract.business_id == business.id)
    if status:
        query = query.where(Contract.status == status)

    contracts_result = await db.execute(query.order_by(Contract.created_at.desc()))
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "customer_id": str(c.customer_id),
            "status": c.status.value if hasattr(c.status, 'value') else c.status,
            "frequency": c.frequency,
            "monthly_price": float(c.monthly_price) if c.monthly_price else None,
            "next_job_date": c.next_job_date.isoformat() if c.next_job_date else None,
            "sla_response_hours": c.sla_response_hours,
        }
        for c in contracts_result.scalars().all()
    ]


@router.post("/{contract_id}/generate-jobs")
async def generate_contract_jobs(
    contract_id: UUID,
    count: int = 12,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate upcoming jobs for a contract"""
    biz_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    result = await db.execute(
        select(Contract).where(
            Contract.id == contract_id,
            Contract.business_id == business.id,
        )
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    from dateutil.rrule import rrule, MONTHLY
    from dateutil.parser import parse

    dates = list(rrule(
        freq=MONTHLY,
        count=count,
        dtstart=contract.start_date,
    ))

    jobs_created = 0
    for dt in dates:
        job = Job(
            business_id=contract.business_id,
            customer_id=contract.customer_id,
            contract_id=contract.id,
            title=f"{contract.title} - Scheduled Visit",
            description=f"Scheduled maintenance visit under contract {contract.title}",
            scheduled_at=dt,
            status="scheduled",
        )
        db.add(job)
        jobs_created += 1

    contract.next_job_date = dates[0] if dates else None
    await db.commit()

    return {"jobs_created": jobs_created, "next_date": dates[0].isoformat() if dates else None}


@router.put("/{contract_id}/pause")
async def pause_contract(
    contract_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    biz_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    result = await db.execute(
        select(Contract).where(
            Contract.id == contract_id,
            Contract.business_id == business.id,
        )
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    contract.status = "paused"
    await db.commit()
    return {"message": "Contract paused"}


@router.put("/{contract_id}/resume")
async def resume_contract(
    contract_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    biz_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    result = await db.execute(
        select(Contract).where(
            Contract.id == contract_id,
            Contract.business_id == business.id,
        )
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    contract.status = "active"
    await db.commit()
    return {"message": "Contract resumed"}
