import random
import string
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.models import User, Business
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/cis", tags=["cis"])


# ─── In-memory stores ────────────────────────────────────────
subcontractors: dict[str, dict] = {}
payments: dict[str, dict] = {}


# ─── Schemas ──────────────────────────────────────────────────
class SubcontractorCreate(BaseModel):
    company_name: str
    utr_number: str
    cis_number: str
    verification_status: str = "pending"
    deduction_rate: int = 20
    contact_name: str
    phone: str
    email: str
    address: str


class SubcontractorUpdate(BaseModel):
    company_name: Optional[str] = None
    utr_number: Optional[str] = None
    cis_number: Optional[str] = None
    verification_status: Optional[str] = None
    deduction_rate: Optional[int] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class VerifyRequest(BaseModel):
    utr: str
    verification_date: str
    verified_by: str


class PaymentCreate(BaseModel):
    subcontractor_id: str
    payment_period: str
    gross_amount: float
    materials_deducted: float
    cis_deduction_rate: int
    cis_deduction_amount: float
    net_payment: float
    payment_date: str
    payment_reference: str


# ─── Helpers ──────────────────────────────────────────────────
def _generate_reg_number() -> str:
    return "CIS-" + "".join(random.choices(string.digits, k=7))


def _generate_payment_ref() -> str:
    return "CISP-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ─── Subcontractor endpoints ──────────────────────────────────
@router.post("/subcontractor/register")
async def register_subcontractor(
    data: SubcontractorCreate,
    current_user: User = Depends(get_current_user),
):
    sub_id = str(len(subcontractors) + 1)
    registration_number = _generate_reg_number()
    subcontractors[sub_id] = {
        "id": sub_id,
        "registration_number": registration_number,
        "company_name": data.company_name,
        "utr_number": data.utr_number,
        "cis_number": data.cis_number,
        "verification_status": data.verification_status,
        "deduction_rate": data.deduction_rate,
        "contact_name": data.contact_name,
        "phone": data.phone,
        "email": data.email,
        "address": data.address,
        "business_id": str(current_user.id),
        "created_at": datetime.utcnow().isoformat(),
    }
    return {"id": sub_id, "registration_number": registration_number}


@router.get("/subcontractor/list")
async def list_subcontractors(
    current_user: User = Depends(get_current_user),
):
    user_subs = [
        s for s in subcontractors.values()
        if s["business_id"] == str(current_user.id)
    ]
    return user_subs


@router.put("/subcontractor/{sub_id}")
async def update_subcontractor(
    sub_id: str,
    data: SubcontractorUpdate,
    current_user: User = Depends(get_current_user),
):
    sub = subcontractors.get(sub_id)
    if not sub or sub["business_id"] != str(current_user.id):
        raise HTTPException(status_code=404, detail="Subcontractor not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        sub[field] = value
    return sub


@router.post("/subcontractor/{sub_id}/verify")
async def verify_subcontractor(
    sub_id: str,
    data: VerifyRequest,
    current_user: User = Depends(get_current_user),
):
    sub = subcontractors.get(sub_id)
    if not sub or sub["business_id"] != str(current_user.id):
        raise HTTPException(status_code=404, detail="Subcontractor not found")

    sub["verification_status"] = "verified"
    sub["verified_at"] = data.verification_date
    sub["verified_by"] = data.verified_by
    sub["utr"] = data.utr

    if sub["deduction_rate"] == 30:
        sub["deduction_rate"] = 20

    return {"message": "Subcontractor verified successfully", "subcontractor": sub}


# ─── Payment endpoints ────────────────────────────────────────
@router.post("/payment/monthly")
async def record_monthly_payment(
    data: PaymentCreate,
    current_user: User = Depends(get_current_user),
):
    sub = subcontractors.get(data.subcontractor_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subcontractor not found")

    payment_id = str(len(payments) + 1)
    payment_ref = data.payment_reference or _generate_payment_ref()
    payments[payment_id] = {
        "id": payment_id,
        "subcontractor_id": data.subcontractor_id,
        "subcontractor_name": sub["company_name"],
        "payment_period": data.payment_period,
        "gross_amount": data.gross_amount,
        "materials_deducted": data.materials_deducted,
        "cis_deduction_rate": data.cis_deduction_rate,
        "cis_deduction_amount": data.cis_deduction_amount,
        "net_payment": data.net_payment,
        "payment_date": data.payment_date,
        "payment_reference": payment_ref,
        "business_id": str(current_user.id),
        "created_at": datetime.utcnow().isoformat(),
    }
    return {"id": payment_id, "payment_reference": payment_ref}


@router.get("/payment/monthly/{period}")
async def get_payments_for_period(
    period: str,
    current_user: User = Depends(get_current_user),
):
    period_payments = [
        p for p in payments.values()
        if p["payment_period"] == period and p["business_id"] == str(current_user.id)
    ]
    return period_payments


@router.post("/payment/{payment_id}/payslip")
async def generate_payslip(
    payment_id: str,
    current_user: User = Depends(get_current_user),
):
    payment = payments.get(payment_id)
    if not payment or payment["business_id"] != str(current_user.id):
        raise HTTPException(status_code=404, detail="Payment not found")

    sub = subcontractors.get(payment["subcontractor_id"], {})

    payslip_text = f"""
CIS PAYSLIP
============
Period: {payment['payment_period']}
Date: {payment['payment_date']}

Subcontractor: {sub.get('company_name', 'N/A')}
UTR: {sub.get('utr_number', 'N/A')}
CIS Number: {sub.get('cis_number', 'N/A')}

Payment Details:
  Gross Amount:        £{payment['gross_amount']:,.2f}
  Materials Deducted:  £{payment['materials_deducted']:,.2f}
  CIS Deduction ({payment['cis_deduction_rate']}%): -£{payment['cis_deduction_amount']:,.2f}
  Net Payment:         £{payment['net_payment']:,.2f}

Reference: {payment['payment_reference']}
"""

    import base64
    pdf_bytes = payslip_text.encode("utf-8")
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

    return {"payslip": pdf_base64, "format": "text/plain"}


# ─── Returns endpoints ────────────────────────────────────────
@router.get("/returns/{period}")
async def get_cis_return(
    period: str,
    current_user: User = Depends(get_current_user),
):
    period_payments = [
        p for p in payments.values()
        if p["payment_period"] == period and p["business_id"] == str(current_user.id)
    ]

    total_gross = sum(p["gross_amount"] for p in period_payments)
    total_materials = sum(p["materials_deducted"] for p in period_payments)
    total_deductions = sum(p["cis_deduction_amount"] for p in period_payments)

    sub_map: dict[str, dict] = {}
    for p in period_payments:
        sid = p["subcontractor_id"]
        if sid not in sub_map:
            sub = subcontractors.get(sid, {})
            sub_map[sid] = {
                "name": sub.get("company_name", "Unknown"),
                "utr": sub.get("utr_number", ""),
                "gross": 0.0,
                "deductions": 0.0,
            }
        sub_map[sid]["gross"] += p["gross_amount"]
        sub_map[sid]["deductions"] += p["cis_deduction_amount"]

    return {
        "period": period,
        "total_gross": total_gross,
        "total_materials": total_materials,
        "total_deductions": total_deductions,
        "subcontractors": list(sub_map.values()),
    }


# ─── Annual summary ───────────────────────────────────────────
@router.get("/annual-summary")
async def get_annual_summary(
    tax_year: str = "2025/26",
    current_user: User = Depends(get_current_user),
):
    year_parts = tax_year.split("/")
    if len(year_parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid tax year format. Use YYYY/YY")

    start_year = int("20" + year_parts[1]) if len(year_parts[1]) == 2 else int(year_parts[1])
    end_year = start_year + 1

    months = []
    for m in range(4, 13):
        months.append(f"{start_year}-{m:02d}")
    for m in range(1, 4):
        months.append(f"{end_year}-{m:02d}")

    total_gross = 0.0
    total_deductions = 0.0
    monthly_breakdown = []

    for month in months:
        month_payments = [
            p for p in payments.values()
            if p["payment_period"] == month and p["business_id"] == str(current_user.id)
        ]
        month_gross = sum(p["gross_amount"] for p in month_payments)
        month_deductions = sum(p["cis_deduction_amount"] for p in month_payments)
        month_net = sum(p["net_payment"] for p in month_payments)
        total_gross += month_gross
        total_deductions += month_deductions

        monthly_breakdown.append({
            "month": month,
            "gross": month_gross,
            "deductions": month_deductions,
            "net": month_net,
            "payment_count": len(month_payments),
        })

    return {
        "tax_year": tax_year,
        "total_gross": total_gross,
        "total_deductions": total_deductions,
        "monthly_breakdown": monthly_breakdown,
    }
