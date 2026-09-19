from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from pydantic import BaseModel
from app.core.database import get_db
from app.models.models import Customer, Business, Job, JobStatus, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/memberships", tags=["memberships"])

# In-memory stores (production: use DB tables)
plans_db: dict[str, dict] = {}
memberships_db: dict[str, dict] = {}

for i, plan in enumerate([
    {
        "id": "plan-basic",
        "name": "Basic",
        "description": "Essential maintenance coverage for homeowners",
        "price_monthly": 29.99,
        "price_yearly": 299.99,
        "features": ["Annual boiler service", "Priority booking", "10% discount on repairs", "1 emergency call/year"],
        "job_priority": False,
        "discount_percent": 10,
        "max_emergency_calls": 1,
    },
    {
        "id": "plan-standard",
        "name": "Standard",
        "description": "Comprehensive coverage for families",
        "price_monthly": 59.99,
        "price_yearly": 599.99,
        "features": ["Bi-annual boiler service", "Priority booking", "15% discount on repairs", "3 emergency calls/year", "Free annual gas safety check"],
        "job_priority": True,
        "discount_percent": 15,
        "max_emergency_calls": 3,
    },
    {
        "id": "plan-premium",
        "name": "Premium",
        "description": "Complete peace of mind with unlimited support",
        "price_monthly": 99.99,
        "price_yearly": 999.99,
        "features": ["Quarterly boiler service", "VIP priority booking", "25% discount on repairs", "Unlimited emergency calls", "Free annual gas safety check", "Free boiler replacement after 10 years"],
        "job_priority": True,
        "discount_percent": 25,
        "max_emergency_calls": 999,
    },
]):
    plans_db[plan["id"]] = plan


class PlanCreate(BaseModel):
    name: str
    description: str
    price_monthly: float
    price_yearly: float
    features: List[str]
    job_priority: bool = False
    discount_percent: int = 0
    max_emergency_calls: int = 0


class PlanResponse(BaseModel):
    id: str
    name: str
    description: str
    price_monthly: float
    price_yearly: float
    features: List[str]
    job_priority: bool
    discount_percent: int
    max_emergency_calls: int


class EnrollRequest(BaseModel):
    customer_id: UUID
    plan_id: str
    billing_cycle: str  # "monthly" | "yearly"
    payment_method_id: Optional[str] = None


class MembershipResponse(BaseModel):
    id: str
    customer_id: UUID
    plan_id: str
    plan_name: str
    billing_cycle: str
    status: str
    enrolled_at: datetime
    next_billing_at: datetime
    next_service_at: Optional[datetime]
    payment_method_id: Optional[str]


class CancelRequest(BaseModel):
    membership_id: str
    reason: Optional[str] = None


class PlanBreakdown(BaseModel):
    plan: str
    count: int
    revenue: float


class BusinessOverview(BaseModel):
    total_members: int
    mrr: float
    plans_breakdown: List[PlanBreakdown]


class ScheduleResult(BaseModel):
    jobs_created: int
    memberships_processed: int


async def get_business_id(user: User, db: AsyncSession) -> UUID:
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business.id


@router.post("/plans", response_model=PlanResponse)
async def create_plan(
    data: PlanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_business_id(current_user, db)
    plan_id = f"plan-{uuid4().hex[:8]}"
    plan = {
        "id": plan_id,
        "name": data.name,
        "description": data.description,
        "price_monthly": data.price_monthly,
        "price_yearly": data.price_yearly,
        "features": data.features,
        "job_priority": data.job_priority,
        "discount_percent": data.discount_percent,
        "max_emergency_calls": data.max_emergency_calls,
    }
    plans_db[plan_id] = plan
    return PlanResponse(**plan)


@router.get("/plans", response_model=List[PlanResponse])
async def list_plans(
    current_user: User = Depends(get_current_user),
):
    return [PlanResponse(**p) for p in plans_db.values()]


@router.post("/enroll", response_model=MembershipResponse)
async def enroll_customer(
    data: EnrollRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business_id = await get_business_id(current_user, db)
    result = await db.execute(
        select(Customer).where(
            Customer.id == data.customer_id,
            Customer.business_id == business_id,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if data.plan_id not in plans_db:
        raise HTTPException(status_code=404, detail="Plan not found")

    for m in memberships_db.values():
        if m["customer_id"] == data.customer_id and m["status"] == "active":
            raise HTTPException(status_code=400, detail="Customer already has an active membership")

    if data.billing_cycle not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail="billing_cycle must be 'monthly' or 'yearly'")

    plan = plans_db[data.plan_id]
    now = datetime.utcnow()
    billing_period = timedelta(days=30) if data.billing_cycle == "monthly" else timedelta(days=365)

    membership_id = f"mem-{uuid4().hex[:8]}"
    membership = {
        "id": membership_id,
        "customer_id": data.customer_id,
        "business_id": business_id,
        "plan_id": data.plan_id,
        "billing_cycle": data.billing_cycle,
        "status": "active",
        "enrolled_at": now,
        "next_billing_at": now + billing_period,
        "next_service_at": now + timedelta(days=7),
        "payment_method_id": data.payment_method_id,
        "emergency_calls_used": 0,
    }
    memberships_db[membership_id] = membership

    return MembershipResponse(
        id=membership_id,
        customer_id=data.customer_id,
        plan_id=data.plan_id,
        plan_name=plan["name"],
        billing_cycle=data.billing_cycle,
        status="active",
        enrolled_at=now,
        next_billing_at=now + billing_period,
        next_service_at=now + timedelta(days=7),
        payment_method_id=data.payment_method_id,
    )


@router.get("/{customer_id}", response_model=MembershipResponse)
async def get_membership(
    customer_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_business_id(current_user, db)
    for m in memberships_db.values():
        if m["customer_id"] == customer_id and m["status"] == "active":
            plan = plans_db.get(m["plan_id"], {})
            return MembershipResponse(
                id=m["id"],
                customer_id=m["customer_id"],
                plan_id=m["plan_id"],
                plan_name=plan.get("name", "Unknown"),
                billing_cycle=m["billing_cycle"],
                status=m["status"],
                enrolled_at=m["enrolled_at"],
                next_billing_at=m["next_billing_at"],
                next_service_at=m.get("next_service_at"),
                payment_method_id=m.get("payment_method_id"),
            )
    raise HTTPException(status_code=404, detail="No active membership found for this customer")


@router.post("/cancel")
async def cancel_membership(
    data: CancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_business_id(current_user, db)
    membership = memberships_db.get(data.membership_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    if membership["status"] != "active":
        raise HTTPException(status_code=400, detail="Membership is not active")

    membership["status"] = "cancelled"
    membership["cancelled_at"] = datetime.utcnow()
    membership["cancel_reason"] = data.reason
    return {"message": "Membership cancelled successfully"}


@router.get("/business/overview", response_model=BusinessOverview)
async def business_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business_id = await get_business_id(current_user, db)
    active = [
        m for m in memberships_db.values()
        if m["business_id"] == business_id and m["status"] == "active"
    ]

    mrr = 0.0
    plan_counts: dict[str, int] = {}
    plan_revenue: dict[str, float] = {}

    for m in active:
        plan = plans_db.get(m["plan_id"], {})
        monthly_price = plan.get("price_monthly", 0)
        if m["billing_cycle"] == "yearly":
            monthly_price = plan.get("price_yearly", 0) / 12

        mrr += monthly_price
        plan_counts[m["plan_id"]] = plan_counts.get(m["plan_id"], 0) + 1
        plan_revenue[m["plan_id"]] = plan_revenue.get(m["plan_id"], 0) + monthly_price

    breakdown = [
        PlanBreakdown(
            plan=plans_db.get(pid, {}).get("name", pid),
            count=count,
            revenue=round(plan_revenue[pid], 2),
        )
        for pid, count in plan_counts.items()
    ]

    return BusinessOverview(
        total_members=len(active),
        mrr=round(mrr, 2),
        plans_breakdown=breakdown,
    )


@router.post("/schedule-recurring", response_model=ScheduleResult)
async def schedule_recurring_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    business_id = await get_business_id(current_user, db)
    now = datetime.utcnow()
    jobs_created = 0
    memberships_processed = 0

    for m in memberships_db.values():
        if m["business_id"] != business_id or m["status"] != "active":
            continue

        next_service = m.get("next_service_at")
        if not next_service or next_service > now:
            continue

        memberships_processed += 1
        plan = plans_db.get(m["plan_id"], {})

        result = await db.execute(
            select(Customer).where(Customer.id == m["customer_id"])
        )
        customer = result.scalar_one_or_none()
        if not customer:
            continue

        job = Job(
            business_id=business_id,
            customer_id=m["customer_id"],
            title=f"Recurring service - {plan.get('name', 'Membership')} plan",
            description=f"Scheduled recurring service for {plan.get('name', 'Membership')} member: {customer.full_name}",
            status=JobStatus.SCHEDULED,
            priority="high" if plan.get("job_priority") else "normal",
            scheduled_at=now + timedelta(days=3),
        )
        db.add(job)
        jobs_created += 1

        billing_period = timedelta(days=30) if m["billing_cycle"] == "monthly" else timedelta(days=365)
        m["next_service_at"] = now + billing_period
        m["next_billing_at"] = now + billing_period

    await db.commit()

    return ScheduleResult(
        jobs_created=jobs_created,
        memberships_processed=memberships_processed,
    )
