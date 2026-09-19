from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from app.core.database import get_db
from app.models.models import (
    Business, User, Job, Customer, Quote, Invoice, Review, Payment
)
from app.schemas import DashboardStats
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return DashboardStats(
            total_jobs=0, active_jobs=0, completed_jobs=0, total_revenue=0,
            pending_quotes=0, pending_invoices=0, total_customers=0,
            reviews_count=0, average_rating=0, revenue_this_month=0, jobs_this_month=0
        )

    bid = business.id
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_jobs = (await db.execute(
        select(func.count(Job.id)).where(Job.business_id == bid)
    )).scalar() or 0

    active_jobs = (await db.execute(
        select(func.count(Job.id)).where(
            Job.business_id == bid,
            Job.status.in_(["scheduled", "in_progress"])
        )
    )).scalar() or 0

    completed_jobs = (await db.execute(
        select(func.count(Job.id)).where(
            Job.business_id == bid,
            Job.status == "completed"
        )
    )).scalar() or 0

    total_revenue = (await db.execute(
        select(func.coalesce(func.sum(Invoice.total), 0))
        .join(Job, Invoice.job_id == Job.id)
        .where(Job.business_id == bid, Invoice.payment_status == "paid")
    )).scalar() or 0

    pending_quotes = (await db.execute(
        select(func.count(Quote.id))
        .join(Job, Quote.job_id == Job.id)
        .where(Job.business_id == bid, Quote.is_accepted == False)
    )).scalar() or 0

    pending_invoices = (await db.execute(
        select(func.count(Invoice.id))
        .join(Job, Invoice.job_id == Job.id)
        .where(Job.business_id == bid, Invoice.payment_status == "pending")
    )).scalar() or 0

    total_customers = (await db.execute(
        select(func.count(Customer.id)).where(
            Customer.business_id == bid, Customer.is_active == True
        )
    )).scalar() or 0

    reviews_count = (await db.execute(
        select(func.count(Review.id))
        .join(Job, Review.job_id == Job.id)
        .where(Job.business_id == bid)
    )).scalar() or 0

    average_rating = (await db.execute(
        select(func.coalesce(func.avg(Review.rating), 0))
        .join(Job, Review.job_id == Job.id)
        .where(Job.business_id == bid)
    )).scalar() or 0

    revenue_this_month = (await db.execute(
        select(func.coalesce(func.sum(Invoice.total), 0))
        .join(Job, Invoice.job_id == Job.id)
        .where(
            Job.business_id == bid,
            Invoice.payment_status == "paid",
            Invoice.created_at >= month_start
        )
    )).scalar() or 0

    jobs_this_month = (await db.execute(
        select(func.count(Job.id)).where(
            Job.business_id == bid,
            Job.created_at >= month_start
        )
    )).scalar() or 0

    return DashboardStats(
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        completed_jobs=completed_jobs,
        total_revenue=float(total_revenue),
        pending_quotes=pending_quotes,
        pending_invoices=pending_invoices,
        total_customers=total_customers,
        reviews_count=reviews_count,
        average_rating=float(average_rating),
        revenue_this_month=float(revenue_this_month),
        jobs_this_month=jobs_this_month
    )
