"""Google Business Profile + Trustpilot review automation for VoiceField.

UK field service SaaS (locale en-GB, GBP, Europe/London).

Google Business Profile endpoints mirror the GBP APIs (accounts.locations,
reviews.list, reviews.reply) with local Review rows as the source of truth.
Trustpilot endpoints mirror the Trustpilot Invitation API flow.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Business, Customer, Job, Review, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/review-platforms", tags=["review-platforms"])

LOCALE = "en-GB"

# ─── Module-level state (in production: persisted per-business + OAuth tokens) ─

_google_state: Dict[str, Any] = {
    "connected": False,
    "location_id": None,
    "location_name": None,
    "rating": None,
    "review_count": 0,
}

# review_id (str) -> {"text": str, "replied_at": iso str}
_google_replies: Dict[str, Dict[str, str]] = {}

_trustpilot_state: Dict[str, Any] = {
    "connected": False,
    "api_key_masked": None,
    "business_unit_id": None,
    "trust_score": None,
}

# invitation_id (str) -> invitation record dict
_trustpilot_invitations: Dict[str, Dict[str, Any]] = {}


# ─── Schemas ───


class GoogleConnectRequest(BaseModel):
    location_id: str = Field(..., min_length=1)


class GoogleReplyRequest(BaseModel):
    review_id: UUID
    reply_text: str = Field(..., min_length=1)


class TrustpilotConnectRequest(BaseModel):
    api_key: str = Field(..., min_length=1)
    business_unit_id: str = Field(..., min_length=1)


class TrustpilotInviteRequest(BaseModel):
    customer_id: UUID
    job_id: UUID
    email: str = Field(..., min_length=3)


class AutoRequestBody(BaseModel):
    job_id: UUID


# ─── Helpers ───


def _mask_key(api_key: str) -> str:
    api_key = api_key.strip()
    if len(api_key) <= 4:
        return "****"
    return "****" + api_key[-4:]


async def _get_owned_business_ids(
    current_user: User, db: AsyncSession
) -> List[Any]:
    result = await db.execute(
        select(Business.id).where(Business.owner_id == current_user.id)
    )
    return list(result.scalars().all())


# ─── Google Business Profile ───


@router.get("/google/status")
async def google_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return GBP connection status with live aggregate rating."""
    if not _google_state.get("connected"):
        return {
            "connected": False,
            "location_name": None,
            "rating": None,
            "review_count": 0,
        }

    # Refresh aggregates from local Review rows for this user's businesses.
    try:
        business_ids = await _get_owned_business_ids(current_user, db)
        if business_ids:
            agg = await db.execute(
                select(
                    func.avg(Review.rating),
                    func.count(Review.id),
                )
                .join(Job, Review.job_id == Job.id)
                .where(Job.business_id.in_(business_ids))
            )
            avg_rating, count = agg.one()
            if count:
                _google_state["review_count"] = int(count)
                _google_state["rating"] = (
                    round(float(avg_rating), 1) if avg_rating is not None else None
                )
    except Exception:
        # Status must never fail because of aggregate computation.
        pass

    return {
        "connected": True,
        "location_name": _google_state.get("location_name"),
        "rating": _google_state.get("rating"),
        "review_count": int(_google_state.get("review_count") or 0),
    }


@router.post("/google/connect")
async def google_connect(
    data: GoogleConnectRequest,
    current_user: User = Depends(get_current_user),
):
    """Connect a GBP location. In production this completes OAuth + location lookup."""
    location_id = data.location_id.strip()
    _google_state.update(
        {
            "connected": True,
            "location_id": location_id,
            # Without a live GBP API call, expose the location id as the name.
            "location_name": location_id,
        }
    )
    return {"connected": True}


@router.post("/google/disconnect")
async def google_disconnect(
    current_user: User = Depends(get_current_user),
):
    _google_state.update(
        {
            "connected": False,
            "location_id": None,
            "location_name": None,
            "rating": None,
            "review_count": 0,
        }
    )
    return {"disconnected": True}


@router.get("/google/reviews")
async def google_reviews(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return recent local Review rows mapped to a GBP-style review payload."""
    business_ids = await _get_owned_business_ids(current_user, db)
    if not business_ids:
        return []

    result = await db.execute(
        select(Review)
        .join(Job, Review.job_id == Job.id)
        .where(Job.business_id.in_(business_ids))
        .order_by(Review.created_at.desc())
        .limit(50)
    )
    reviews = list(result.scalars().all())
    if not reviews:
        return []

    # Resolve author names in a single query (en-GB display names).
    customer_ids = list({r.customer_id for r in reviews if r.customer_id})
    names: Dict[Any, str] = {}
    if customer_ids:
        cust_result = await db.execute(
            select(Customer).where(Customer.id.in_(customer_ids))
        )
        for customer in cust_result.scalars().all():
            names[customer.id] = customer.full_name

    mapped = []
    for review in reviews:
        rid = str(review.id)
        author = names.get(review.customer_id) or review.title or "Anonymous"
        text = review.content or review.title or ""
        created_at = (
            review.created_at.isoformat() if review.created_at is not None else None
        )
        mapped.append(
            {
                "id": rid,
                "author": author,
                "rating": review.rating,
                "text": text,
                "created_at": created_at,
                "responded": rid in _google_replies,
            }
        )
    return mapped


@router.post("/google/reply")
async def google_reply(
    data: GoogleReplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reply to a review. Persists locally; in production calls GBP reviews.reply."""
    business_ids = await _get_owned_business_ids(current_user, db)
    result = await db.execute(
        select(Review)
        .join(Job, Review.job_id == Job.id)
        .where(
            Review.id == data.review_id,
            Job.business_id.in_(business_ids) if business_ids else False,
        )
    )
    review = result.scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    reply_text = data.reply_text.strip()
    if not reply_text:
        raise HTTPException(status_code=400, detail="reply_text must not be empty")

    # Update local Review with response. The Review model has no dedicated
    # response column, so track the owner reply in module state and attach it
    # transiently for downstream readers; commit to close the transaction.
    _google_replies[str(review.id)] = {
        "text": reply_text,
        "replied_at": datetime.utcnow().isoformat(),
        "locale": LOCALE,
    }
    try:
        setattr(review, "response", reply_text)
    except Exception:
        pass
    await db.commit()

    # In production: POST https://mybusiness.googleapis.com/v4/{review_name}/reply
    return {"success": True}


# ─── Trustpilot ───


@router.get("/trustpilot/status")
async def trustpilot_status(
    current_user: User = Depends(get_current_user),
):
    if not _trustpilot_state.get("connected"):
        return {
            "connected": False,
            "business_unit_id": None,
            "trust_score": None,
        }
    return {
        "connected": True,
        "business_unit_id": _trustpilot_state.get("business_unit_id"),
        "trust_score": _trustpilot_state.get("trust_score"),
    }


@router.post("/trustpilot/connect")
async def trustpilot_connect(
    data: TrustpilotConnectRequest,
    current_user: User = Depends(get_current_user),
):
    """Store Trustpilot credentials (key masked, never returned)."""
    _trustpilot_state.update(
        {
            "connected": True,
            "api_key_masked": _mask_key(data.api_key),
            "business_unit_id": data.business_unit_id.strip(),
        }
    )
    return {"connected": True}


@router.post("/trustpilot/invite")
async def trustpilot_invite(
    data: TrustpilotInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Trustpilot review invitation for a completed job customer."""
    # In production this would call the Trustpilot Invitation API:
    # POST https://invitations-api.trustpilot.com/v1/private/business-units/
    #   {businessUnitId}/email-invitations with locale en-GB.
    business_unit_id: Optional[str] = _trustpilot_state.get("business_unit_id")

    invitation_id = str(uuid4())
    record: Dict[str, Any] = {
        "invitation_id": invitation_id,
        "business_unit_id": business_unit_id,
        "customer_id": str(data.customer_id),
        "job_id": str(data.job_id),
        "email": data.email,
        "locale": LOCALE,
        "status": "sent",
        "owner_id": str(current_user.id),
        "created_at": datetime.utcnow().isoformat(),
    }
    _trustpilot_invitations[invitation_id] = record
    return {"invitation_id": invitation_id, "status": "sent"}


@router.get("/trustpilot/invitations")
async def trustpilot_invitations(
    current_user: User = Depends(get_current_user),
):
    """List sent Trustpilot invitations for the business."""
    owner_id = str(current_user.id)
    return [
        {k: v for k, v in record.items() if k != "owner_id"}
        for record in _trustpilot_invitations.values()
        if record.get("owner_id") == owner_id
    ]


# ─── Shared ───


@router.post("/auto-request")
async def auto_request(
    data: AutoRequestBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """After job completion, queue review requests across connected platforms."""
    business_ids = await _get_owned_business_ids(current_user, db)
    result = await db.execute(
        select(Job).where(
            Job.id == data.job_id,
            Job.business_id.in_(business_ids) if business_ids else False,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    queued: List[str] = []

    # Google review link (GBP share/review URL for the connected location).
    if _google_state.get("connected"):
        queued.append("google")

    # Trustpilot invite — queue an invitation record alongside the email.
    if _trustpilot_state.get("connected"):
        queued.append("trustpilot")
        customer_email: Optional[str] = None
        if job.customer_id is not None:
            cust = await db.execute(
                select(Customer).where(Customer.id == job.customer_id)
            )
            customer = cust.scalar_one_or_none()
            if customer is not None:
                customer_email = customer.email
        invitation_id = str(uuid4())
        _trustpilot_invitations[invitation_id] = {
            "invitation_id": invitation_id,
            "business_unit_id": _trustpilot_state.get("business_unit_id"),
            "customer_id": str(job.customer_id) if job.customer_id else None,
            "job_id": str(job.id),
            "email": customer_email,
            "locale": LOCALE,
            "status": "sent",
            "owner_id": str(current_user.id),
            "created_at": datetime.utcnow().isoformat(),
            "source": "auto-request",
        }

    # Transactional email with review links (en-GB template) always queued.
    queued.append("email")

    # In production: enqueue background tasks (email/SMS + platform invites).
    return {"queued": queued, "job_id": str(data.job_id)}
