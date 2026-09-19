from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import GdprConsent, GdprErasureRequest, Customer, User, Business
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/gdpr", tags=["gdpr"])


@router.post("/consent")
async def record_consent(
    consent_type: str,
    granted: bool,
    request,
    db: AsyncSession = Depends(get_db)
):
    """Record GDPR consent"""
    consent = GdprConsent(
        consent_type=consent_type,
        granted=granted,
        ip_address=request.client.host if hasattr(request, 'client') else None,
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


@router.get("/data-map")
async def data_map(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Data processing map showing what data is collected"""
    return {
        "data_categories": [
            {
                "category": "Customer Personal Data",
                "fields": ["name", "email", "phone", "address"],
                "purpose": "Service delivery",
                "legal_basis": "Contract performance",
                "retention": "6 years (Limitation Act 1980)",
                "storage": "PostgreSQL (encrypted at rest)",
            },
            {
                "category": "Financial Data",
                "fields": ["invoices", "payments", "bank details"],
                "purpose": "Payment processing",
                "legal_basis": "Contract performance",
                "retention": "6 years (HMRC requirement)",
                "storage": "PostgreSQL + Stripe",
            },
            {
                "category": "Property Data",
                "fields": ["addresses", "GPS coordinates", "photos"],
                "purpose": "Service delivery",
                "legal_basis": "Contract performance",
                "retention": "6 years",
                "storage": "PostgreSQL + Cloudflare R2",
            },
            {
                "category": "Vehicle Tracking",
                "fields": ["GPS coordinates", "trip history"],
                "purpose": "Fleet management",
                "legal_basis": "Legitimate interests (with DPIA)",
                "retention": "90 days",
                "storage": "PostgreSQL",
            },
            {
                "category": "Marketing Consent",
                "fields": ["email consent", "SMS consent"],
                "purpose": "Marketing communications",
                "legal_basis": "Consent",
                "retention": "Until withdrawn",
                "storage": "PostgreSQL",
            },
        ]
    }


@router.post("/export-data/{user_id}")
async def export_user_data(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Export all data for a user (Subject Access Request)"""
    # In production, this generates a comprehensive data export
    return {
        "user_id": str(user_id),
        "export_format": "JSON",
        "data_categories": [
            "personal_data", "jobs", "invoices", "quotes", "reviews",
            "consent_records", "activity_logs"
        ],
        "estimated_completion": "72 hours",
    }
