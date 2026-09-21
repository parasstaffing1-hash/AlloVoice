from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from app.core.database import get_db
from app.models.models import (
    Customer, Job, Business, User, Review, Property,
    JobStatus, Contract, ContractStatus, Feedback
)
from app.routes.auth import get_current_user
from app.services import llm

router = APIRouter(prefix="/api/ai-insights", tags=["ai-insights"])


async def get_business_id(user: User, db: AsyncSession) -> UUID:
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business.id


# ─── Schemas ───────────────────────────────────────────

class ChurnPredictRequest(BaseModel):
    customer_id: str


class RetainCampaignRequest(BaseModel):
    customer_ids: List[str]
    campaign_type: str = Field(..., pattern="^(discount|follow_up|maintenance_reminder)$")


class ReviewRespondRequest(BaseModel):
    review_id: str
    review_text: str
    rating: int = Field(..., ge=1, le=5)
    customer_name: str


class BulkReviewRespondRequest(BaseModel):
    reviews: List[ReviewRespondRequest]


class UpsellGenerateRequest(BaseModel):
    job_type: str
    job_description: str
    customer_id: str
    property_details: Optional[dict] = None


class UpsellCompletionRequest(BaseModel):
    job_id: str


# ─── Churn Prediction Helpers ──────────────────────────

async def get_customer_history(customer_id: UUID, db: AsyncSession):
    now = datetime.utcnow()
    result = await db.execute(
        select(Job).where(Job.customer_id == customer_id).order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()

    if not jobs:
        return {
            "last_job_date": None,
            "job_count": 0,
            "total_spend": 0.0,
            "avg_job_value": 0.0,
            "days_since_last_job": 999,
            "completed_job_count": 0,
            "recent_job_statuses": [],
        }

    last_job = jobs[0]
    completed = [j for j in jobs if j.status in (JobStatus.COMPLETED, JobStatus.PAID)]
    total_spend = sum(float(j.final_cost or j.estimated_cost or 0) for j in completed)
    avg_value = total_spend / len(completed) if completed else 0
    days_since = (now - last_job.created_at).days if last_job.created_at else 999

    return {
        "last_job_date": last_job.created_at.isoformat() if last_job.created_at else None,
        "job_count": len(jobs),
        "completed_job_count": len(completed),
        "total_spend": total_spend,
        "avg_job_value": avg_value,
        "days_since_last_job": days_since,
        "recent_job_statuses": [j.status.value for j in jobs[:5]],
    }


def calculate_churn_score(history: dict, has_membership: bool, complaint_count: int) -> dict:
    score = 0.0
    factors = []
    now = datetime.utcnow()

    # Days since last job
    days = history["days_since_last_job"]
    if days > 180:
        score += 0.35
        factors.append({
            "factor": "Days Since Last Job",
            "weight": 0.35,
            "description": f"No job in {days} days — well past typical return window"
        })
    elif days > 90:
        score += 0.20
        factors.append({
            "factor": "Days Since Last Job",
            "weight": 0.20,
            "description": f"Last job was {days} days ago — approaching at-risk window"
        })
    else:
        factors.append({
            "factor": "Days Since Last Job",
            "weight": 0.0,
            "description": f"Active within {days} days"
        })

    # Job frequency trend
    if history["job_count"] >= 3:
        score += 0.15
        factors.append({
            "factor": "Returning Customer",
            "weight": 0.15,
            "description": f"Customer has {history['job_count']} jobs on record"
        })
    elif history["job_count"] == 1:
        score += 0.25
        factors.append({
            "factor": "One-Time Customer",
            "weight": 0.25,
            "description": "Only one job completed — higher churn risk for new customers"
        })

    # Cancelled jobs in recent history
    cancelled = [s for s in history["recent_job_statuses"] if s == "cancelled"]
    if cancelled:
        score += 0.10
        factors.append({
            "factor": "Cancelled Jobs",
            "weight": 0.10,
            "description": f"{len(cancelled)} recent job(s) were cancelled"
        })

    # Membership
    if has_membership:
        score -= 0.20
        factors.append({
            "factor": "Active Membership",
            "weight": -0.20,
            "description": "Customer has an active membership — significantly lowers churn risk"
        })
    else:
        factors.append({
            "factor": "No Membership",
            "weight": 0.05,
            "description": "No active membership — more likely to churn"
        })
        score += 0.05

    # Complaints / feedback
    if complaint_count > 0:
        score += min(complaint_count * 0.10, 0.20)
        factors.append({
            "factor": "Recent Complaints",
            "weight": min(complaint_count * 0.10, 0.20),
            "description": f"{complaint_count} complaint(s) recorded"
        })

    # Low spend customer
    if history["total_spend"] > 0 and history["avg_job_value"] < 100:
        score += 0.05
        factors.append({
            "factor": "Low Average Spend",
            "weight": 0.05,
            "description": f"Average job value of £{history['avg_job_value']:.2f} is below typical"
        })

    score = max(0.0, min(1.0, score))

    if score >= 0.70:
        risk_level = "critical"
    elif score >= 0.45:
        risk_level = "high"
    elif score >= 0.20:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Predicted churn date
    if risk_level == "critical":
        churn_date = now + timedelta(days=14)
    elif risk_level == "high":
        churn_date = now + timedelta(days=30)
    elif risk_level == "medium":
        churn_date = now + timedelta(days=60)
    else:
        churn_date = now + timedelta(days=120)

    return {
        "risk_level": risk_level,
        "risk_score": round(score, 2),
        "factors": factors,
        "predicted_churn_date": churn_date.isoformat(),
    }


def get_retention_actions(risk_level: str, factors: list) -> list:
    actions = []
    if risk_level in ("critical", "high"):
        actions.append("Send personalised discount code (10-15% off next job)")
        actions.append("Phone call from business owner within 24 hours")
        actions.append("Offer free inspection or maintenance check")
    if risk_level == "medium":
        actions.append("Send maintenance reminder email")
        actions.append("Offer loyalty reward for repeat booking")
    if risk_level == "low":
        actions.append("Continue regular communication")
        actions.append("Invite to leave a review")

    has_complaint = any(f["factor"] == "Recent Complaints" and f["weight"] > 0 for f in factors)
    if has_complaint:
        actions.insert(0, "Resolve any outstanding complaints immediately")

    no_membership = any(f["factor"] == "No Membership" for f in factors)
    if no_membership:
        actions.append("Offer membership plan with priority booking")

    return actions


# ─── Churn Endpoints ───────────────────────────────────

@router.post("/churn/predict")
async def predict_churn(
    data: ChurnPredictRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    customer_id = UUID(data.customer_id)

    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.business_id == business_id
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    history = await get_customer_history(customer_id, db)

    # Check membership
    membership_result = await db.execute(
        select(Contract).where(
            Contract.customer_id == customer_id,
            Contract.business_id == business_id,
            Contract.status == ContractStatus.ACTIVE
        )
    )
    has_membership = membership_result.scalar_one_or_none() is not None

    # Check complaints
    complaint_result = await db.execute(
        select(Feedback).where(
            Feedback.customer_id == customer_id,
            Feedback.feedback_type == "complaint"
        )
    )
    complaint_count = len(complaint_result.scalars().all())

    churn = calculate_churn_score(history, has_membership, complaint_count)
    actions = get_retention_actions(churn["risk_level"], churn["factors"])

    return {
        "risk_level": churn["risk_level"],
        "risk_score": churn["risk_score"],
        "factors": churn["factors"],
        "recommended_actions": actions,
        "last_job_date": history["last_job_date"],
        "days_since_last_job": history["days_since_last_job"],
        "total_spend": history["total_spend"],
        "predicted_churn_date": churn["predicted_churn_date"],
    }


@router.get("/churn/segment")
async def segment_customers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)

    result = await db.execute(
        select(Customer).where(Customer.business_id == business_id, Customer.is_active == True)
    )
    customers = result.scalars().all()

    segments = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    customer_list = []

    for customer in customers:
        history = await get_customer_history(customer.id, db)

        membership_result = await db.execute(
            select(Contract).where(
                Contract.customer_id == customer.id,
                Contract.business_id == business_id,
                Contract.status == ContractStatus.ACTIVE
            )
        )
        has_membership = membership_result.scalar_one_or_none() is not None

        complaint_result = await db.execute(
            select(Feedback).where(
                Feedback.customer_id == customer.id,
                Feedback.feedback_type == "complaint"
            )
        )
        complaint_count = len(complaint_result.scalars().all())

        churn = calculate_churn_score(history, has_membership, complaint_count)
        segments[churn["risk_level"]] += 1

        customer_list.append({
            "id": str(customer.id),
            "name": customer.full_name,
            "risk_level": churn["risk_level"],
            "risk_score": churn["risk_score"],
            "last_contact": history["last_job_date"],
        })

    customer_list.sort(key=lambda x: x["risk_score"], reverse=True)

    return {
        "low": segments["low"],
        "medium": segments["medium"],
        "high": segments["high"],
        "critical": segments["critical"],
        "customers": customer_list,
    }


@router.post("/churn/retain")
async def generate_retention_campaign(
    data: RetainCampaignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    business_id = await get_business_id(current_user, db)
    messages = []

    for cid_str in data.customer_ids:
        cid = UUID(cid_str)
        result = await db.execute(
            select(Customer).where(
                Customer.id == cid,
                Customer.business_id == business_id
            )
        )
        customer = result.scalar_one_or_none()
        if not customer:
            continue

        history = await get_customer_history(cid, db)
        first_name = customer.full_name.split()[0] if customer.full_name else "there"

        if data.campaign_type == "discount":
            message = (
                f"Hi {first_name}, we've missed you at Allo! "
                f"As a valued customer, we'd like to offer you 15% off your next job. "
                f"Use code WELCOME15 when booking. Offer valid for 30 days."
            )
            channel = "email"
            if customer.phone:
                channel = "sms"

        elif data.campaign_type == "follow_up":
            days = history["days_since_last_job"]
            message = (
                f"Hi {first_name}, it's been {days} days since your last job with us. "
                f"Just checking in to see if there's anything we can help with. "
                f"We'd love to have you back!"
            )
            channel = "sms"
            if not customer.phone:
                channel = "email"

        else:  # maintenance_reminder
            message = (
                f"Hi {first_name}, it's a great time to book your regular maintenance. "
                f"Keeping on top of maintenance saves money long-term. "
                f"Would you like to schedule a check-up? Reply YES to get started."
            )
            channel = "email"
            if customer.phone:
                channel = "sms"

        messages.append({
            "customer_id": cid_str,
            "message": message,
            "channel": channel,
        })

    estimated_cost = len(messages) * 0.03  # Approximate SMS/email cost

    return {
        "campaign": {
            "name": f"{data.campaign_type.replace('_', ' ').title()} Campaign — {len(messages)} customers",
            "messages": messages,
            "estimated_cost": round(estimated_cost, 2),
        }
    }


# ─── Review Response Helpers ───────────────────────────

REVIEW_SYSTEM_PROMPT = (
    "You write Google review replies for a UK trades business. Professional, warm, "
    "plain UK English. 5 stars: thank + mention specifics + invite back. "
    "3-4: thank + acknowledge concerns. 1-2: apologise, offer resolution with "
    "phone placeholder, no defensiveness. Max 3 sentences."
)


async def _get_business_name_for_review(user: User, db) -> str:
    """Best-effort business name lookup for LLM prompts. Never raises."""
    try:
        result = await db.execute(select(Business).where(Business.owner_id == user.id))
        business = result.scalar_one_or_none()
        if business is not None and getattr(business, "name", None):
            return str(business.name)
    except Exception:
        pass
    return "Allo"


def analyze_sentiment(text: str, rating: int) -> str:
    text_lower = text.lower() if text else ""
    negative_words = ["bad", "terrible", "awful", "horrible", "worst", "rude", "late", "poor", "disappointed", "waste"]
    positive_words = ["great", "excellent", "fantastic", "brilliant", "amazing", "recommend", "professional", "prompt", "quality"]

    neg_count = sum(1 for w in negative_words if w in text_lower)
    pos_count = sum(1 for w in positive_words if w in text_lower)

    if rating <= 2 or neg_count > pos_count:
        return "negative"
    elif rating >= 4 or pos_count > neg_count:
        return "positive"
    return "neutral"


def generate_review_response(review_text: str, rating: int, customer_name: str) -> dict:
    sentiment = analyze_sentiment(review_text, rating)
    first_name = customer_name.split()[0] if customer_name else "there"

    if rating >= 5:
        response = (
            f"Thank you so much for the wonderful review, {first_name}! "
            f"We're thrilled to hear about your positive experience with our team. "
            f"Your kind words mean a great deal to us. We look forward to serving you again soon!"
        )
        suggested_action = "Share on social media"

    elif rating == 4:
        response = (
            f"Thank you for your review, {first_name}. We're glad we could meet your expectations. "
            f"If there's anything we could do even better next time, we'd love to hear your thoughts. "
            f"We appreciate your continued support!"
        )
        suggested_action = "Send thank you message"

    elif rating == 3:
        response = (
            f"Thank you for your honest feedback, {first_name}. "
            f"We appreciate you taking the time to share your experience. "
            f"We're always working to improve our service, and your comments help us do just that. "
            f"Please don't hesitate to get in touch if there's anything we can address."
        )
        suggested_action = "Follow up with customer"

    else:
        response = (
            f"We're truly sorry to hear about your experience, {first_name}. "
            f"This is not the standard we strive for at Allo. "
            f"We'd like to make this right — please contact us directly on 0800 123 4567 "
            f"so we can resolve this matter promptly. Your satisfaction is our priority."
        )
        suggested_action = "Escalate to owner immediately"

    return {
        "response_text": response,
        "sentiment": sentiment,
        "suggested_action": suggested_action,
    }


# ─── Review Endpoints ──────────────────────────────────

@router.post("/reviews/respond")
async def respond_to_review(
    data: ReviewRespondRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    fallback = generate_review_response(data.review_text, data.rating, data.customer_name)
    if llm.is_configured():
        try:
            business_name = await _get_business_name_for_review(current_user, db)
            prompt = (
                f"Business name: {business_name}\n"
                f"Customer name: {data.customer_name}\n"
                f"Star rating: {data.rating}/5\n"
                f"Review text: {data.review_text}"
            )
            llm_text = await llm.complete(
                prompt,
                system=REVIEW_SYSTEM_PROMPT,
                max_tokens=300,
                temperature=0.3,
            )
            if llm_text and llm_text.strip():
                return {
                    "response_text": llm_text.strip(),
                    "sentiment": fallback["sentiment"],
                    "suggested_action": fallback["suggested_action"],
                }
        except Exception:
            pass
    return fallback


@router.post("/reviews/bulk-respond")
async def bulk_respond_to_reviews(
    data: BulkReviewRespondRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    responses = []
    llm_available = llm.is_configured()
    business_name = "Allo"
    if llm_available:
        try:
            business_name = await _get_business_name_for_review(current_user, db)
        except Exception:
            business_name = "Allo"
            llm_available = False
    for review in data.reviews:
        fallback = generate_review_response(review.review_text, review.rating, review.customer_name)
        response_text = fallback["response_text"]
        if llm_available:
            try:
                prompt = (
                    f"Business name: {business_name}\n"
                    f"Customer name: {review.customer_name}\n"
                    f"Star rating: {review.rating}/5\n"
                    f"Review text: {review.review_text}"
                )
                llm_text = await llm.complete(
                    prompt,
                    system=REVIEW_SYSTEM_PROMPT,
                    max_tokens=300,
                    temperature=0.3,
                )
                if llm_text and llm_text.strip():
                    response_text = llm_text.strip()
            except Exception:
                response_text = fallback["response_text"]
        responses.append({
            "review_id": review.review_id,
            "response_text": response_text,
            "sentiment": fallback["sentiment"],
        })

    return {"responses": responses}


# ─── Upsell Helpers ────────────────────────────────────

UPSELL_CATALOG = {
    "boiler_install": [
        {"title": "Annual Boiler Service", "description": "Keep your boiler running efficiently with an annual service. Prevents breakdowns and maintains warranty.", "price_range": "£80-£120", "priority": "high", "reason": "New boilers benefit from early servicing", "confidence": 0.9},
        {"title": "Powerflush", "description": "Full central heating powerflush to remove sludge and improve heating efficiency.", "price_range": "£300-£500", "priority": "medium", "reason": "Recommended for new installations to maximise lifespan", "confidence": 0.7},
        {"title": "Smart Thermostat Installation", "description": "Upgrade to a Hive or Nest smart thermostat for better control and energy savings.", "price_range": "£150-£250", "priority": "medium", "reason": "Complements a new boiler installation", "confidence": 0.75},
        {"title": "Magnetic Filter", "description": "Install a magnetic system filter to protect your new boiler from debris.", "price_range": "£80-£150", "priority": "high", "reason": "Extends boiler lifespan and maintains efficiency", "confidence": 0.85},
    ],
    "gas_safety": [
        {"title": "Boiler Service Add-On", "description": "Add an annual boiler service to your gas safety check for comprehensive coverage.", "price_range": "£60-£90", "priority": "high", "reason": "Customers needing gas safety often need servicing too", "confidence": 0.8},
        {"title": "Gas Cooker Installation", "description": "Professional gas cooker installation with safety certificate.", "price_range": "£80-£120", "priority": "medium", "reason": "Related gas appliance service", "confidence": 0.6},
    ],
    "electrical": [
        {"title": "Full EICR Certificate", "description": "Electrical Installation Condition Report for landlords or home safety.", "price_range": "£150-£250", "priority": "high", "reason": "Complementary electrical safety service", "confidence": 0.7},
        {"title": "Outdoor Socket Installation", "description": "Weatherproof outdoor socket for garden or workshop use.", "price_range": "£120-£200", "priority": "medium", "reason": "Common add-on during electrical work", "confidence": 0.65},
    ],
    "plumbing": [
        {"title": "Bathroom Silicone Refresh", "description": "Remove old silicone and apply fresh sealant around bath, shower, and sink.", "price_range": "£60-£100", "priority": "medium", "reason": "Often needed during plumbing maintenance", "confidence": 0.6},
        {"title": "Water Heater Flush", "description": "Annual immersion heater flush to remove scale and improve performance.", "price_range": "£50-£80", "priority": "low", "reason": "Preventive maintenance for water heaters", "confidence": 0.5},
    ],
    "general": [
        {"title": "Annual Maintenance Plan", "description": "Priority booking, discounted rates, and peace of mind with our annual maintenance plan.", "price_range": "£15/month", "priority": "high", "reason": "Convert one-off customers to recurring revenue", "confidence": 0.7},
        {"title": "Emergency Cover Package", "description": "24/7 emergency callout cover with reduced callout fees.", "price_range": "£10/month", "priority": "medium", "reason": "Adds value and recurring revenue", "confidence": 0.6},
    ],
}


def match_upsell_to_job(job_type: str, job_description: str, customer_jobs: list) -> list:
    job_type_lower = job_type.lower()
    job_desc_lower = job_description.lower() if job_description else ""

    suggestions = []

    # Match by job type keyword
    for key, upsells in UPSELL_CATALOG.items():
        if key.replace("_", " ") in job_type_lower or key.replace("_", " ") in job_desc_lower:
            suggestions.extend(upsells)

    # Always include general upsells if nothing specific matched
    if not suggestions:
        suggestions = UPSELL_CATALOG["general"]

    # Filter out already purchased services
    purchased_titles = set()
    for cj in customer_jobs:
        title_lower = (cj.title or "").lower()
        purchased_titles.add(title_lower)

    filtered = []
    for s in suggestions:
        if s["title"].lower() not in purchased_titles:
            filtered.append(s)

    return filtered


# ─── Upsell Endpoints ──────────────────────────────────

@router.post("/upsell/generate")
async def generate_upsell_suggestions(
    data: UpsellGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    customer_id = UUID(data.customer_id)

    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    job_result = await db.execute(
        select(Job).where(Job.customer_id == customer_id).order_by(Job.created_at.desc())
    )
    customer_jobs = job_result.scalars().all()

    suggestions = match_upsell_to_job(data.job_type, data.job_description, customer_jobs)

    total_potential = 0.0
    for s in suggestions:
        price_str = s["price_range"].replace("£", "").replace(",", "")
        if "month" in s["price_range"]:
            try:
                total_potential += float(price_str.replace("/month", "")) * 12
            except ValueError:
                pass
        elif "-" in price_str:
            parts = price_str.split("-")
            try:
                total_potential += (float(parts[0]) + float(parts[1])) / 2
            except ValueError:
                pass
        else:
            try:
                total_potential += float(price_str)
            except ValueError:
                pass

    return {
        "suggestions": suggestions,
        "total_potential_revenue": round(total_potential, 2),
    }


@router.post("/upsell/on-completion")
async def upsell_on_completion(
    data: UpsellCompletionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    job_id = UUID(data.job_id)

    result = await db.execute(
        select(Job).where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_result = await db.execute(
        select(Job).where(Job.customer_id == job.customer_id).order_by(Job.created_at.desc())
    )
    customer_jobs = job_result.scalars().all()

    suggestions = match_upsell_to_job(job.title or "", job.description or "", customer_jobs)

    cross_sells = []
    for s in suggestions:
        if s["priority"] == "high":
            cross_sells.append({
                "title": s["title"],
                "description": f"Customers who booked {job.title} also saved with: {s['title']}",
                "price_range": s["price_range"],
            })

    return {
        "suggestions": suggestions,
        "cross_sells": cross_sells,
    }
