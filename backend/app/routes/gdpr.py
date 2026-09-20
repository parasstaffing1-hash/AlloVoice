from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import (
    GdprConsent,
    GdprErasureRequest,
    Customer,
    User,
    Business,
    Job,
    Invoice,
    Quote,
    Property,
    Payment,
    FleetTrip,
    FleetVehicle,
)
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/gdpr", tags=["gdpr"])


@router.post("/consent")
async def record_consent(
    consent_type: str,
    granted: bool,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Record GDPR consent (GdprConsent.user_id is NOT NULL → must pass it)."""
    consent = GdprConsent(
        user_id=current_user.id,
        consent_type=consent_type,
        granted=granted,
        ip_address=request.client.host if getattr(request, "client", None) else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(consent)
    await db.commit()
    return {"success": True}


@router.get("/consent-status")
async def consent_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(GdprConsent).where(GdprConsent.user_id == current_user.id)
    )
    consents = result.scalars().all()
    return {
        "consents": [
            {"type": c.consent_type, "granted": c.granted, "date": c.created_at.isoformat()}
            for c in consents
        ]
    }


@router.post("/erasure-request")
async def request_erasure(
    customer_id: UUID = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Request data erasure (Right to be forgotten)"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    erasure = GdprErasureRequest(
        business_id=business.id,
        customer_id=customer_id,
        user_id=current_user.id if not customer_id else None,
        status="pending",
    )
    db.add(erasure)

    if customer_id:
        cust_result = await db.execute(select(Customer).where(Customer.id == customer_id))
        customer = cust_result.scalar_one_or_none()
        if customer:
            customer.gdpr_erasure_requested = True
            customer.gdpr_erasure_at = datetime.utcnow()
            # Anonymize personal data
            customer.full_name = "REDACTED"
            customer.email = None
            customer.phone = "REDACTED"
            customer.notes = None
            customer.company = None

    await db.commit()
    return {"message": "Erasure request submitted", "status": "pending"}


@router.post("/erasure-request/{request_id}/process")
async def process_erasure(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Process an erasure request"""
    result = await db.execute(select(GdprErasureRequest).where(GdprErasureRequest.id == request_id))
    erasure = result.scalar_one_or_none()
    if not erasure:
        raise HTTPException(status_code=404, detail="Request not found")

    erasure.status = "processed"
    erasure.processed_at = datetime.utcnow()
    await db.commit()
    return {"message": "Erasure request processed"}


def _column_names(model, exclude=("id", "created_at", "updated_at")) -> list:
    """Field names derived from the SQLAlchemy model (stays truthful)."""
    return [c.name for c in model.__table__.columns if c.name not in exclude]


def _deduped(*lists) -> list:
    seen, out = set(), []
    for lst in lists:
        for item in lst:
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


@router.get("/data-map")
async def data_map(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Data processing map showing what data is collected.

    Field lists are derived from the SQLAlchemy models; retention periods
    are estimates (confirm with legal counsel) and labelled as such.
    """
    return {
        "note": "Retention periods below are estimates — confirm with legal counsel.",
        "data_categories": [
            {
                "category": "Customer Personal Data",
                "fields": _column_names(Customer),
                "purpose": "Service delivery",
                "legal_basis": "Contract performance",
                "retention": "6 years (estimate — Limitation Act 1980)",
                "storage": f"PostgreSQL table '{Customer.__tablename__}' (encrypted at rest)",
            },
            {
                "category": "Financial Data",
                "fields": _deduped(_column_names(Invoice), _column_names(Payment)),
                "purpose": "Payment processing",
                "legal_basis": "Contract performance",
                "retention": "6 years (estimate — HMRC requirement)",
                "storage": (
                    f"PostgreSQL tables '{Invoice.__tablename__}', "
                    f"'{Payment.__tablename__}' + Stripe (only when card "
                    "payments are configured)"
                ),
            },
            {
                "category": "Property Data",
                "fields": _column_names(Property),
                "purpose": "Service delivery",
                "legal_basis": "Contract performance",
                "retention": "6 years (estimate)",
                "storage": (
                    f"PostgreSQL table '{Property.__tablename__}' + Cloudflare R2 "
                    "(job photos only)"
                ),
            },
            {
                "category": "Vehicle Tracking",
                "fields": _deduped(_column_names(FleetVehicle), _column_names(FleetTrip)),
                "purpose": "Fleet management",
                "legal_basis": "Legitimate interests (with DPIA)",
                "retention": "90 days (estimate)",
                "storage": (
                    f"PostgreSQL tables '{FleetVehicle.__tablename__}', "
                    f"'{FleetTrip.__tablename__}'"
                ),
            },
            {
                "category": "Marketing Consent",
                "fields": _deduped(_column_names(GdprConsent), ["marketing_consent (customers)"]),
                "purpose": "Marketing communications",
                "legal_basis": "Consent",
                "retention": "Until withdrawn (estimate)",
                "storage": (
                    f"PostgreSQL tables '{GdprConsent.__tablename__}', "
                    f"'{Customer.__tablename__}'"
                ),
            },
        ],
    }


@router.post("/export-data/{user_id}")
async def export_user_data(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Export all data for a user/customer (Subject Access Request).

    Returns a real inline JSON export assembled from the database — no
    waiting period. The requested id must be the caller or a customer of a
    business the caller owns, otherwise 403.
    """
    def _status(value):
        return value.value if hasattr(value, "value") else value

    def _job_dict(j: Job) -> dict:
        return {
            "id": str(j.id),
            "title": j.title,
            "status": _status(j.status),
            "scheduled_at": j.scheduled_at.isoformat() if j.scheduled_at else None,
            "started_at": j.started_at.isoformat() if getattr(j, "started_at", None) else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }

    def _invoice_dict(i: Invoice) -> dict:
        return {
            "id": str(i.id),
            "invoice_number": i.invoice_number,
            "total": float(i.total),
            "status": _status(i.payment_status),
            "due_date": i.due_date.isoformat() if i.due_date else None,
        }

    def _quote_dict(q: Quote) -> dict:
        return {
            "id": str(q.id),
            "quote_number": q.quote_number,
            "title": q.title,
            "total": float(q.total),
            "is_accepted": q.is_accepted,
        }

    async def _consents_for(user_id_value) -> list:
        result = await db.execute(
            select(GdprConsent).where(GdprConsent.user_id == user_id_value)
        )
        return [
            {
                "type": c.consent_type,
                "granted": c.granted,
                "date": c.created_at.isoformat() if c.created_at else None,
            }
            for c in result.scalars().all()
        ]

    if user_id == current_user.id:
        # Self export: profile + owned businesses and their records.
        biz_result = await db.execute(
            select(Business).where(Business.owner_id == current_user.id)
        )
        businesses = list(biz_result.scalars().all())
        business_ids = [b.id for b in businesses]
        customers, jobs, invoices, quotes = [], [], [], []
        if business_ids:
            cust_result = await db.execute(
                select(Customer).where(Customer.business_id.in_(business_ids))
            )
            customers = list(cust_result.scalars().all())
            customer_ids = [c.id for c in customers]
            if customer_ids:
                jobs_result = await db.execute(
                    select(Job).where(Job.customer_id.in_(customer_ids))
                )
                jobs = list(jobs_result.scalars().all())
                inv_result = await db.execute(
                    select(Invoice).where(Invoice.customer_id.in_(customer_ids))
                )
                invoices = list(inv_result.scalars().all())
                quotes_result = await db.execute(
                    select(Quote).where(Quote.customer_id.in_(customer_ids))
                )
                quotes = list(quotes_result.scalars().all())
        return {
            "format": "json",
            "data": {
                "user": {
                    "id": str(current_user.id),
                    "email": current_user.email,
                    "full_name": current_user.full_name,
                    "phone": current_user.phone,
                },
                "businesses": [
                    {"id": str(b.id), "name": b.name} for b in businesses
                ],
                "customers": [
                    {
                        "id": str(c.id),
                        "full_name": c.full_name,
                        "email": c.email,
                        "phone": c.phone,
                    }
                    for c in customers
                ],
                "jobs": [_job_dict(j) for j in jobs],
                "invoices": [_invoice_dict(i) for i in invoices],
                "quotes": [_quote_dict(q) for q in quotes],
                "consents": await _consents_for(current_user.id),
                "exported_at": datetime.utcnow().isoformat(),
            },
        }

    # Customer export: must belong to a business the caller owns.
    cust_result = await db.execute(select(Customer).where(Customer.id == user_id))
    customer = cust_result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=403, detail="Access denied")
    biz_result = await db.execute(select(Business).where(Business.id == customer.business_id))
    business = biz_result.scalar_one_or_none()
    if business is None or business.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    jobs_result = await db.execute(select(Job).where(Job.customer_id == customer.id))
    inv_result = await db.execute(select(Invoice).where(Invoice.customer_id == customer.id))
    quotes_result = await db.execute(select(Quote).where(Quote.customer_id == customer.id))
    return {
        "format": "json",
        "data": {
            "customer": {
                "id": str(customer.id),
                "full_name": customer.full_name,
                "email": customer.email,
                "phone": customer.phone,
                "company": customer.company,
                "marketing_consent": customer.marketing_consent,
            },
            "jobs": [_job_dict(j) for j in jobs_result.scalars().all()],
            "invoices": [_invoice_dict(i) for i in inv_result.scalars().all()],
            "quotes": [_quote_dict(q) for q in quotes_result.scalars().all()],
            # Consent rows are keyed by login user, not customers, so a
            # customer has no separate consent rows; opt-in lives on the
            # profile above.
            "consents": [],
            "exported_at": datetime.utcnow().isoformat(),
        },
    }
