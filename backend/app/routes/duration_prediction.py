import statistics
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import User, Job, Business, JobStatus
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


async def get_business_id(user: User, db: AsyncSession) -> UUID:
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business.id


def calculate_duration_stats(durations: list[int]) -> dict:
    if not durations:
        return {"mean": 60, "median": 60, "std": 0, "count": 0}
    return {
        "mean": round(statistics.mean(durations)),
        "median": round(statistics.median(durations)),
        "std": round(statistics.stdev(durations)) if len(durations) > 1 else 0,
        "count": len(durations)
    }


def apply_duration_modifiers(base_minutes: int, factors: list[dict]) -> tuple[int, list[dict]]:
    modified = base_minutes
    for factor in factors:
        if factor.get("apply"):
            impact_pct = factor.get("impact_pct", 0)
            modified = round(modified * (1 + impact_pct / 100))
    return modified, factors


@router.post("/duration")
async def predict_duration(
    job_type: str,
    property_type: str = "residential",
    property_age: str = "",
    scope_description: str = "",
    property_size: str = "",
    is_emergency: bool = False,
    is_first_visit: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)

    result = await db.execute(
        select(Job).where(
            Job.business_id == business_id,
            Job.status.in_([JobStatus.COMPLETED, JobStatus.PAID, JobStatus.INVOICED])
        ).order_by(Job.completed_at.desc()).limit(200)
    )
    completed_jobs = result.scalars().all()

    durations = []
    for job in completed_jobs:
        if job.started_at and job.completed_at:
            delta = (job.completed_at - job.started_at).total_seconds() / 60
            if 10 < delta < 1440:
                durations.append(round(delta))

    stats = calculate_duration_stats(durations)

    base_minutes = stats["median"] if stats["count"] > 0 else 60

    factors = []
    age_lower = property_age.lower() if property_age else ""
    if age_lower in ("old", "vintage", "pre-1970", "victorian", "edwardian"):
        factors.append({"factor": "Older property", "impact": "+20%", "apply": True, "impact_pct": 20})
    if is_emergency:
        factors.append({"factor": "Emergency call-out", "impact": "+30%", "apply": True, "impact_pct": 30})
    if is_first_visit:
        factors.append({"factor": "First visit to property", "impact": "+15%", "apply": True, "impact_pct": 15})

    predicted, _ = apply_duration_modifiers(base_minutes, factors)

    confidence = min(0.95, 0.5 + (stats["count"] * 0.05)) if stats["count"] > 0 else 0.3
    spread = max(15, round(predicted * 0.25))

    return {
        "predicted_minutes": predicted,
        "confidence": round(confidence, 2),
        "range_min": max(10, predicted - spread),
        "range_max": predicted + spread,
        "based_on": stats["count"],
        "factors": [{"factor": f["factor"], "impact": f["impact"]} for f in factors]
    }


@router.post("/cost")
async def predict_cost(
    job_type: str,
    property_type: str = "residential",
    property_age: str = "",
    scope_description: str = "",
    property_size: str = "",
    budget_range: str = "mid",
    is_emergency: bool = False,
    is_first_visit: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)

    result = await db.execute(
        select(Job).where(
            Job.business_id == business_id,
            Job.status.in_([JobStatus.COMPLETED, JobStatus.PAID, JobStatus.INVOICED]),
            Job.final_cost.isnot(None)
        ).order_by(Job.completed_at.desc()).limit(200)
    )
    completed_jobs = result.scalars().all()

    costs = []
    for job in completed_jobs:
        if job.final_cost and float(job.final_cost) > 0:
            costs.append(float(job.final_cost))

    if costs:
        avg_cost = statistics.mean(costs)
        median_cost = statistics.median(costs)
    else:
        avg_cost = 150.0
        median_cost = 150.0

    base_cost = median_cost

    if budget_range == "low":
        base_cost *= 0.7
    elif budget_range == "high":
        base_cost *= 1.4

    age_lower = property_age.lower() if property_age else ""
    if age_lower in ("old", "vintage", "pre-1970", "victorian", "edwardian"):
        base_cost *= 1.15
    if is_emergency:
        base_cost *= 1.25
    if is_first_visit:
        base_cost *= 1.10

    labour_pct = 0.45
    materials_pct = 0.40
    vat_rate = 0.20

    labour = round(base_cost * labour_pct, 2)
    materials = round(base_cost * materials_pct, 2)
    subtotal = labour + materials
    vat = round(subtotal * vat_rate, 2)
    total = round(subtotal + vat, 2)

    confidence = min(0.9, 0.4 + (len(costs) * 0.04)) if costs else 0.25

    return {
        "estimated_cost": total,
        "breakdown": {
            "labour": labour,
            "materials": materials,
            "vat": vat
        },
        "confidence": round(confidence, 2)
    }


@router.get("/accuracy")
async def prediction_accuracy(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)

    result = await db.execute(
        select(Job).where(
            Job.business_id == business_id,
            Job.status.in_([JobStatus.COMPLETED, JobStatus.PAID, JobStatus.INVOICED]),
            Job.started_at.isnot(None),
            Job.completed_at.isnot(None)
        ).order_by(Job.completed_at.desc()).limit(100)
    )
    jobs = result.scalars().all()

    deviations = []
    for job in jobs:
        actual = (job.completed_at - job.started_at).total_seconds() / 60
        if job.estimated_cost and actual > 10:
            if job.started_at and job.completed_at:
                predicted = float(job.estimated_cost) / 1.5
                deviation = abs(actual - predicted)
                deviations.append(deviation)

    avg_deviation = round(statistics.mean(deviations), 1) if deviations else 0
    within_20pct = sum(1 for d in deviations if d < 30)
    accuracy = round((within_20pct / len(deviations)) * 100, 1) if deviations else 0

    return {
        "avg_deviation_minutes": avg_deviation,
        "accuracy_pct": accuracy,
        "total_predictions": len(deviations)
    }
