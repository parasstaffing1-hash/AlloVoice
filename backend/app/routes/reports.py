from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from datetime import datetime, timedelta
from app.core.database import get_db
from app.models.models import (
    Job, Invoice, Customer, Review, Business, User,
    ActivityTimeline, Contract, Feedback
)
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/revenue")
async def revenue_report(
    period: str = "monthly",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Revenue report by period"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return {"data": []}

    now = datetime.utcnow()
    if period == "daily":
        start = now - timedelta(days=30)
    elif period == "weekly":
        start = now - timedelta(weeks=12)
    else:
        start = now - timedelta(days=365)

    inv_result = await db.execute(
        select(Invoice)
        .join(Customer)
        .where(
            Customer.business_id == business.id,
            Invoice.created_at >= start,
            Invoice.payment_status == "paid",
        )
    )
    invoices = inv_result.scalars().all()

    # Group by period
    data = {}
    for inv in invoices:
        key = inv.created_at.strftime("%Y-%m") if period == "monthly" else inv.created_at.strftime("%Y-%W")
        if key not in data:
            data[key] = {"period": key, "revenue": 0, "count": 0}
        data[key]["revenue"] += float(inv.total)
        data[key]["count"] += 1

    return {"data": list(data.values()), "currency": "GBP"}


@router.get("/technician-performance")
async def technician_performance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Technician performance metrics"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return {"data": []}

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0)

    from app.models.models import Technician
    techs_result = await db.execute(
        select(Technician).where(Technician.business_id == business.id)
    )
    techs = techs_result.scalars().all()

    performance = []
    for tech in techs:
        jobs_completed = await db.execute(
            select(func.count(Job.id)).where(
                Job.technician_id == tech.id,
                Job.status == "completed",
                Job.completed_at >= month_start,
            )
        )
        avg_rating = await db.execute(
            select(func.avg(Review.rating))
            .join(Job)
            .where(Job.technician_id == tech.id)
        )
        performance.append({
            "technician_id": str(tech.id),
            "jobs_completed": jobs_completed.scalar() or 0,
            "average_rating": float(avg_rating.scalar() or 0),
        })

    return {"data": performance}


@router.get("/customer-satisfaction")
async def customer_satisfaction(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return {"average_rating": 0, "nps": 0, "total_reviews": 0}

    avg_result = await db.execute(
        select(func.avg(Review.rating))
        .join(Job)
        .where(Job.business_id == business.id)
    )
    avg_rating = avg_result.scalar() or 0

    total_result = await db.execute(
        select(func.count(Review.id))
        .join(Job)
        .where(Job.business_id == business.id)
    )
    total = total_result.scalar() or 0

    nps_result = await db.execute(
        select(func.avg(Feedback.nps_score))
        .where(
            Feedback.business_id == business.id,
            Feedback.nps_score.isnot(None),
        )
    )
    nps = nps_result.scalar() or 0

    return {
        "average_rating": float(avg_rating),
        "nps": float(nps),
        "total_reviews": total,
    }


@router.get("/job-utilization")
async def job_utilization(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Job utilization rates"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return {"data": []}

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0)

    total_jobs = await db.execute(
        select(func.count(Job.id)).where(
            Job.business_id == business.id,
            Job.created_at >= month_start,
        )
    )
    completed = await db.execute(
        select(func.count(Job.id)).where(
            Job.business_id == business.id,
            Job.status == "completed",
            Job.completed_at >= month_start,
        )
    )
    cancelled = await db.execute(
        select(func.count(Job.id)).where(
            Job.business_id == business.id,
            Job.status == "cancelled",
            Job.created_at >= month_start,
        )
    )

    total = total_jobs.scalar() or 0
    comp = completed.scalar() or 0
    canc = cancelled.scalar() or 0

    return {
        "total_jobs": total,
        "completed": comp,
        "cancelled": canc,
        "completion_rate": (comp / total * 100) if total else 0,
    }
