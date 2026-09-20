from typing import Optional

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import Customer, Quote, Invoice, Job, User, Review, PaymentStatus
from app.routes.auth import get_current_user
from app.services.auth import create_access_token, decode_access_token

router = APIRouter(prefix="/api/portal", tags=["portal"])
settings = get_settings()


@router.post("/auth")
async def portal_auth(
    email: str,
    token: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate customer via magic link or token"""
    if token:
        result = await db.execute(
            select(Customer).where(
                Customer.portal_token == token,
                Customer.portal_enabled == True,
                Customer.is_active == True,
            )
        )
        customer = result.scalar_one_or_none()
        if customer:
            return {
                "authenticated": True,
                "customer_id": str(customer.id),
                "customer_name": customer.full_name,
            }

    if email:
        result = await db.execute(
            select(Customer).where(
                Customer.email == email,
                Customer.portal_enabled == True,
                Customer.is_active == True,
            )
        )
        customer = result.scalar_one_or_none()
        if customer:
            # In production, send magic link email
            return {"magic_link_sent": True, "email": email}

    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.get("/quotes")
async def portal_quotes(
    customer_id: UUID,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Get quotes for portal customer"""
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.portal_token == token,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=401, detail="Unauthorized")

    quotes_result = await db.execute(
        select(Quote).where(Quote.customer_id == customer_id).order_by(Quote.created_at.desc())
    )
    return [
        {
            "id": str(q.id),
            "quote_number": q.quote_number,
            "title": q.title,
            "total": float(q.total),
            "is_accepted": q.is_accepted,
            "valid_until": q.valid_until.isoformat() if q.valid_until else None,
            "created_at": q.created_at.isoformat(),
        }
        for q in quotes_result.scalars().all()
    ]


@router.get("/invoices")
async def portal_invoices(
    customer_id: Optional[UUID] = None,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db)
):
    """Get invoices for portal customer.

    Two auth modes share this single path (only one route per method+path
    is possible): a Bearer portal JWT (from POST /api/portal/login) takes
    precedence and returns the portal shape; otherwise the legacy
    customer_id + portal-token query params apply with unchanged behavior.
    """
    if authorization and authorization.lower().startswith("bearer "):
        customer = await _portal_customer_from_bearer(authorization[7:].strip(), db)
        inv_result = await db.execute(
            select(Invoice).where(Invoice.customer_id == customer.id).order_by(Invoice.created_at.desc())
        )
        return [
            {
                "id": str(i.id),
                "invoice_number": i.invoice_number,
                "total": float(i.total),
                "status": _enum_value(i.payment_status),
                "due_date": i.due_date.isoformat() if i.due_date else None,
                "download_url": None,
            }
            for i in inv_result.scalars().all()
        ]

    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.portal_token == token,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=401, detail="Unauthorized")

    inv_result = await db.execute(
        select(Invoice).where(Invoice.customer_id == customer_id).order_by(Invoice.created_at.desc())
    )
    return [
        {
            "id": str(i.id),
            "invoice_number": i.invoice_number,
            "total": float(i.total),
            "amount_paid": float(i.amount_paid),
            "payment_status": i.payment_status.value if hasattr(i.payment_status, 'value') else i.payment_status,
            "due_date": i.due_date.isoformat() if i.due_date else None,
            "created_at": i.created_at.isoformat(),
        }
        for i in inv_result.scalars().all()
    ]


@router.get("/jobs")
async def portal_jobs(
    customer_id: UUID,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Get jobs for portal customer"""
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.portal_token == token,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=401, detail="Unauthorized")

    jobs_result = await db.execute(
        select(Job).where(Job.customer_id == customer_id).order_by(Job.created_at.desc())
    )
    return [
        {
            "id": str(j.id),
            "title": j.title,
            "status": j.status.value if hasattr(j.status, 'value') else j.status,
            "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "created_at": j.created_at.isoformat(),
        }
        for j in jobs_result.scalars().all()
    ]


@router.post("/quotes/{quote_id}/accept")
async def portal_accept_quote(
    quote_id: UUID,
    customer_id: UUID,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Accept a quote from the portal"""
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.portal_token == token,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=401, detail="Unauthorized")

    quote_result = await db.execute(
        select(Quote).where(Quote.id == quote_id, Quote.customer_id == customer_id)
    )
    quote = quote_result.scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote.is_accepted = True
    quote.accepted_at = datetime.utcnow()
    await db.commit()

    return {"message": "Quote accepted"}


# ─── Bearer-token portal (frontend: /portal/login + dashboard) ──────────────

_portal_bearer = HTTPBearer(auto_error=False)


def _enum_value(value):
    """Unwrap str-enum columns to plain strings (None-safe)."""
    return value.value if hasattr(value, "value") else value


async def _portal_customer_from_bearer(token: str, db: AsyncSession) -> Customer:
    """Decode a portal JWT and load its customer. 401 JSON on any failure."""
    payload = decode_access_token(token) if token else None
    if not payload or payload.get("scope") != "portal" or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid portal token")
    try:
        customer_id = UUID(str(payload["sub"]))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid portal token")
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.is_active == True,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid portal token")
    return customer


async def get_portal_customer(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_portal_bearer),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing portal token")
    return await _portal_customer_from_bearer(credentials.credentials, db)


def _stripe_usable() -> bool:
    """True only when a real Stripe secret key is configured (mirrors payments.py)."""
    key = (settings.STRIPE_SECRET_KEY or "").strip()
    return bool(key) and "xxx" not in key.lower()


def _portal_job_dict(j: Job) -> dict:
    return {
        "id": str(j.id),
        "title": j.title,
        "status": _enum_value(j.status),
        "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }


class PortalLoginRequest(BaseModel):
    access_code: str


class PortalReviewRequest(BaseModel):
    rating: int
    title: Optional[str] = None
    content: Optional[str] = None


@router.post("/login")
async def portal_login(data: PortalLoginRequest, db: AsyncSession = Depends(get_db)):
    """Customer portal login via short access code.

    ACCESS CODE SCHEME (documented contract): the access code is the first
    8 characters of the customer's UUID, i.e. ``str(customer.id)[:8]``
    (matched case-insensitively). Stable because UUIDs never change.
    """
    code = (data.access_code or "").strip().lower()
    if not code:
        raise HTTPException(status_code=401, detail="Invalid access code")
    result = await db.execute(select(Customer).where(Customer.is_active == True))
    match: Optional[Customer] = None
    for candidate in result.scalars().all():
        if str(candidate.id)[:8].lower() == code:
            match = candidate
            break
    if match is None:
        raise HTTPException(status_code=401, detail="Invalid access code")
    token = create_access_token({"sub": str(match.id), "scope": "portal"})
    return {
        "token": token,
        "customer_id": str(match.id),
        "customer_name": match.full_name,
    }


@router.get("/dashboard")
async def portal_dashboard(
    customer: Customer = Depends(get_portal_customer),
    db: AsyncSession = Depends(get_db),
):
    """Portal dashboard for the Bearer-authenticated customer."""
    jobs_result = await db.execute(
        select(Job)
        .where(Job.customer_id == customer.id)
        .order_by(Job.created_at.desc())
        .limit(20)
    )
    jobs = list(jobs_result.scalars().all())
    completed_statuses = {"completed", "invoiced", "paid"}

    def _status(j: Job) -> str:
        return str(_enum_value(j.status))

    open_jobs = [_portal_job_dict(j) for j in jobs if _status(j) not in completed_statuses and _status(j) != "cancelled"]
    upcoming_jobs = [_portal_job_dict(j) for j in jobs if _status(j) in ("scheduled", "in_progress")]
    completed_jobs = [_portal_job_dict(j) for j in jobs if _status(j) in completed_statuses]

    inv_result = await db.execute(
        select(Invoice)
        .where(
            Invoice.customer_id == customer.id,
            Invoice.payment_status != PaymentStatus.PAID,
        )
        .order_by(Invoice.created_at.desc())
    )
    unpaid_invoices = [
        {
            "id": str(i.id),
            "invoice_number": i.invoice_number,
            "total": float(i.total),
            "status": _enum_value(i.payment_status),
            "due_date": i.due_date.isoformat() if i.due_date else None,
            "download_url": None,
        }
        for i in inv_result.scalars().all()
    ]

    quotes_result = await db.execute(
        select(Quote)
        .where(Quote.customer_id == customer.id)
        .order_by(Quote.created_at.desc())
        .limit(5)
    )
    recent_quotes = [
        {
            "id": str(q.id),
            "quote_number": q.quote_number,
            "title": q.title,
            "total": float(q.total),
            "is_accepted": q.is_accepted,
            "valid_until": q.valid_until.isoformat() if q.valid_until else None,
        }
        for q in quotes_result.scalars().all()
    ]

    return {
        "customer": {
            "id": str(customer.id),
            "name": customer.full_name,
            "email": customer.email,
            "phone": customer.phone,
        },
        "open_jobs": open_jobs,
        "upcoming_jobs": upcoming_jobs,
        "completed_jobs": completed_jobs,
        "unpaid_invoices": unpaid_invoices,
        "recent_quotes": recent_quotes,
    }


@router.post("/invoices/{invoice_id}/pay")
async def portal_pay_invoice(
    invoice_id: UUID,
    customer: Customer = Depends(get_portal_customer),
    db: AsyncSession = Depends(get_db),
):
    """Pay a portal invoice. Without Stripe keys this honestly reports 402
    (never a fake success); with keys it creates a Checkout Session like
    payments.py does and returns {checkout_url}."""
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.customer_id == customer.id,
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not _stripe_usable():
        return JSONResponse(
            status_code=402,
            content={
                "detail": "Online payment not enabled yet — please pay by bank transfer",
                "invoice_number": invoice.invoice_number,
                "total": float(invoice.total),
            },
        )

    checkout_kwargs: dict = {
        "mode": "payment",
        "line_items": [
            {
                "price_data": {
                    "currency": "gbp",
                    "product_data": {"name": f"Invoice {invoice.invoice_number}"},
                    "unit_amount": int(round(float(invoice.total) * 100)),
                },
                "quantity": 1,
            }
        ],
        "metadata": {"invoice_id": str(invoice_id)},
        "success_url": f"{settings.APP_URL}/portal?paid={invoice_id}",
        "cancel_url": f"{settings.APP_URL}/portal",
    }
    if getattr(customer, "email", None):
        checkout_kwargs["customer_email"] = customer.email
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(**checkout_kwargs)
    except Exception:
        raise HTTPException(status_code=502, detail="Stripe request failed")
    try:
        getter = getattr(session, "get", None)
        checkout_url = getter("url") if callable(getter) else getattr(session, "url", None)
    except Exception:
        checkout_url = None
    if not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe request failed")
    return {"checkout_url": checkout_url}


@router.post("/jobs/{job_id}/review")
async def portal_review_job(
    job_id: UUID,
    data: PortalReviewRequest,
    customer: Customer = Depends(get_portal_customer),
    db: AsyncSession = Depends(get_db),
):
    """Leave a review for a completed portal job (rating 1-5)."""
    if data.rating < 1 or data.rating > 5:
        raise HTTPException(status_code=400, detail="rating must be between 1 and 5")
    job_result = await db.execute(
        select(Job).where(Job.id == job_id, Job.customer_id == customer.id)
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    review = Review(
        job_id=job.id,
        customer_id=customer.id,
        rating=data.rating,
        title=data.title,
        content=data.content,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return {
        "id": str(review.id),
        "job_id": str(review.job_id),
        "customer_id": str(review.customer_id),
        "rating": review.rating,
        "title": review.title,
        "content": review.content,
    }
