import io
import csv
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import Customer, Job, Invoice, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/import-export", tags=["import-export"])


@router.post("/import/customers")
async def import_customers_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Import customers from CSV file"""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be CSV")

    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    imported = 0
    errors = []
    for i, row in enumerate(reader, 1):
        try:
            customer = Customer(
                business_id=business.id,
                full_name=row.get("name", row.get("full_name", "")),
                email=row.get("email", ""),
                phone=row.get("phone", ""),
                company=row.get("company", ""),
                notes=row.get("notes", ""),
            )
            db.add(customer)
            imported += 1
        except Exception as e:
            errors.append({"row": i, "error": str(e)})

    await db.commit()
    return {"imported": imported, "errors": errors}


@router.post("/import/jobs")
async def import_jobs_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Import jobs from CSV file"""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be CSV")

    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    imported = 0
    for row in reader:
        job = Job(
            business_id=business.id,
            title=row.get("title", "Imported Job"),
            description=row.get("description", ""),
            status=row.get("status", "quote_requested"),
        )
        db.add(job)
        imported += 1

    await db.commit()
    return {"imported": imported}


@router.get("/export/customers")
async def export_customers_csv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Export customers as CSV"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    customers_result = await db.execute(
        select(Customer).where(Customer.business_id == business.id)
    )
    customers = customers_result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "email", "phone", "company", "notes", "created_at"])
    for c in customers:
        writer.writerow([
            c.full_name, c.email or "", c.phone, c.company or "",
            c.notes or "", c.created_at.strftime("%d/%m/%Y") if c.created_at else ""
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=customers_{datetime.now().strftime('%Y%m%d')}.csv"},
    )


@router.get("/export/jobs")
async def export_jobs_csv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Export jobs as CSV"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    jobs_result = await db.execute(
        select(Job).where(Job.business_id == business.id).order_by(Job.created_at.desc())
    )
    jobs = jobs_result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["title", "status", "priority", "scheduled_at", "estimated_cost", "created_at"])
    for j in jobs:
        writer.writerow([
            j.title, j.status.value if hasattr(j.status, 'value') else j.status,
            j.priority, j.scheduled_at.strftime("%d/%m/%Y %H:%M") if j.scheduled_at else "",
            float(j.estimated_cost) if j.estimated_cost else "",
            j.created_at.strftime("%d/%m/%Y") if j.created_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=jobs_{datetime.now().strftime('%Y%m%d')}.csv"},
    )


@router.get("/export/invoices")
async def export_invoices_csv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Export invoices as CSV"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    inv_result = await db.execute(
        select(Invoice).join(Customer).where(
            Customer.business_id == business.id
        ).order_by(Invoice.created_at.desc())
    )
    invoices = inv_result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["invoice_number", "total", "amount_paid", "payment_status", "due_date", "created_at"])
    for inv in invoices:
        writer.writerow([
            inv.invoice_number, float(inv.total), float(inv.amount_paid),
            inv.payment_status.value if hasattr(inv.payment_status, 'value') else inv.payment_status,
            inv.due_date.strftime("%d/%m/%Y") if inv.due_date else "",
            inv.created_at.strftime("%d/%m/%Y") if inv.created_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=invoices_{datetime.now().strftime('%Y%m%d')}.csv"},
    )
