from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
from enum import Enum
import random
import string
import base64
from io import BytesIO

from app.core.database import get_db
from app.routes.auth import get_current_user
from app.services import storage as r2

router = APIRouter(prefix="/api/compliance", tags=["compliance"])

# --- Enums ---
class EquipmentType(str, Enum):
    split_system = "split_system"
    multi_split = "multi_split"
    vrf = "vrf"
    heat_pump = "heat_pump"
    refrigeration = "refrigeration"

class GasType(str, Enum):
    R32 = "R32"
    R410A = "R410A"
    R407C = "R407C"
    R134A = "R134A"
    R290 = "R290"

class LeakCheckResult(str, Enum):
    pass_ = "pass"
    fail = "fail"

class LeakCheckMethod(str, Enum):
    electronic = "electronic"
    visual = "visual"
    bubble = "bubble"

class PropertyType(str, Enum):
    domestic = "domestic"
    commercial = "commercial"

class BoilerType(str, Enum):
    combi = "combi"
    system = "system"
    regular = "regular"
    back_boiler = "back_boiler"

class FlueType(str, Enum):
    balanced = "balanced"
    open = "open"
    room_sealed = "room_sealed"

class GasCondition(str, Enum):
    satisfactory = "satisfactory"
    unsatisfactory = "unsatisfactory"

# --- F-Gas Models ---
class SafetyTestResult(BaseModel):
    appliance: str
    test_result: str
    defect_found: str
    action_required: str

class FGasCreate(BaseModel):
    customer_id: str
    job_id: Optional[str] = None
    property_address: str
    equipment_type: EquipmentType
    equipment_location: str
    make_model: str
    serial_number: str
    gas_type: GasType
    leak_check_result: LeakCheckResult
    leak_check_method: LeakCheckMethod
    quantity_kg: float
    next_leak_check_date: str
    engineer_name: str
    engineer_signature_url: Optional[str] = None
    notes: Optional[str] = None

class FGasResponse(BaseModel):
    id: str
    certificate_number: str
    customer_id: str
    job_id: Optional[str]
    property_address: str
    equipment_type: str
    equipment_location: str
    make_model: str
    serial_number: str
    gas_type: str
    leak_check_result: str
    leak_check_method: str
    quantity_kg: float
    next_leak_check_date: str
    engineer_name: str
    engineer_signature_url: Optional[str]
    notes: Optional[str]
    status: str
    created_at: str
    original_id: Optional[str] = None

# --- Gas Safety Models ---
class GasSafetyCreate(BaseModel):
    customer_id: str
    property_address: str
    property_type: PropertyType
    boiler_make: str
    boiler_model: str
    boiler_type: BoilerType
    boiler_location: str
    flue_type: FlueType
    gas_supply_condition: GasCondition
    ventilation_condition: GasCondition
    safety_test_results: List[SafetyTestResult]
    gas_safe_registered_number: str
    next_check_date: str

class GasSafetyResponse(BaseModel):
    id: str
    certificate_number: str
    customer_id: str
    property_address: str
    property_type: str
    boiler_make: str
    boiler_model: str
    boiler_type: str
    boiler_location: str
    flue_type: str
    gas_supply_condition: str
    ventilation_condition: str
    safety_test_results: List[SafetyTestResult]
    gas_safe_registered_number: str
    next_check_date: str
    status: str
    created_at: str

# --- In-memory storage ---
fgas_certificates: dict[str, dict] = {}
gas_safety_certificates: dict[str, dict] = {}

# --- Helpers ---
def generate_certificate_number(prefix: str) -> str:
    year = datetime.now().year
    random_part = "".join(random.choices(string.digits, k=5))
    return f"{prefix}-{year}-{random_part}"

def generate_id() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=12))

def get_status(next_check_date_str: str) -> str:
    next_date = datetime.strptime(next_check_date_str, "%Y-%m-%d")
    now = datetime.now()
    if next_date < now:
        return "expired"
    elif next_date < now + timedelta(days=30):
        return "expiring_soon"
    elif next_date < now + timedelta(days=90):
        return "warning"
    return "valid"

# --- F-Gas Endpoints ---
@router.post("/fgas/create", response_model=FGasResponse)
def create_fgas_certificate(data: FGasCreate, user=Depends(get_current_user)):
    cert_id = generate_id()
    cert_number = generate_certificate_number("FGAS")
    now = datetime.now().isoformat()

    cert = {
        "id": cert_id,
        "certificate_number": cert_number,
        "customer_id": data.customer_id,
        "job_id": data.job_id,
        "property_address": data.property_address,
        "equipment_type": data.equipment_type.value,
        "equipment_location": data.equipment_location,
        "make_model": data.make_model,
        "serial_number": data.serial_number,
        "gas_type": data.gas_type.value,
        "leak_check_result": data.leak_check_result.value,
        "leak_check_method": data.leak_check_method.value,
        "quantity_kg": data.quantity_kg,
        "next_leak_check_date": data.next_leak_check_date,
        "engineer_name": data.engineer_name,
        "engineer_signature_url": data.engineer_signature_url,
        "notes": data.notes,
        "status": get_status(data.next_leak_check_date),
        "created_at": now,
        "original_id": None,
    }
    fgas_certificates[cert_id] = cert
    return FGasResponse(**cert)

@router.get("/fgas/list")
def list_fgas_certificates(
    status: Optional[str] = Query(None),
    property_address: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    results = list(fgas_certificates.values())
    if status:
        results = [c for c in results if c["status"] == status]
    if property_address:
        results = [c for c in results if property_address.lower() in c["property_address"].lower()]
    if date_from:
        results = [c for c in results if c["created_at"][:10] >= date_from]
    if date_to:
        results = [c for c in results if c["created_at"][:10] <= date_to]
    return results

@router.get("/fgas/expiring")
def get_expiring_fgas(user=Depends(get_current_user)):
    now = datetime.now()
    threshold = now + timedelta(days=30)
    results = []
    for cert in fgas_certificates.values():
        next_date = datetime.strptime(cert["next_leak_check_date"], "%Y-%m-%d")
        if now <= next_date <= threshold:
            results.append(cert)
    return results

@router.get("/fgas/{cert_id}", response_model=FGasResponse)
def get_fgas_certificate(cert_id: str, user=Depends(get_current_user)):
    if cert_id not in fgas_certificates:
        raise HTTPException(status_code=404, detail="F-Gas certificate not found")
    return FGasResponse(**fgas_certificates[cert_id])

@router.post("/fgas/{cert_id}/renew", response_model=FGasResponse)
def renew_fgas_certificate(cert_id: str, data: FGasCreate, user=Depends(get_current_user)):
    if cert_id not in fgas_certificates:
        raise HTTPException(status_code=404, detail="Original F-Gas certificate not found")

    new_id = generate_id()
    cert_number = generate_certificate_number("FGAS")
    now = datetime.now().isoformat()

    cert = {
        "id": new_id,
        "certificate_number": cert_number,
        "customer_id": data.customer_id,
        "job_id": data.job_id,
        "property_address": data.property_address,
        "equipment_type": data.equipment_type.value,
        "equipment_location": data.equipment_location,
        "make_model": data.make_model,
        "serial_number": data.serial_number,
        "gas_type": data.gas_type.value,
        "leak_check_result": data.leak_check_result.value,
        "leak_check_method": data.leak_check_method.value,
        "quantity_kg": data.quantity_kg,
        "next_leak_check_date": data.next_leak_check_date,
        "engineer_name": data.engineer_name,
        "engineer_signature_url": data.engineer_signature_url,
        "notes": data.notes,
        "status": get_status(data.next_leak_check_date),
        "created_at": now,
        "original_id": cert_id,
    }
    fgas_certificates[new_id] = cert
    return FGasResponse(**cert)

# --- Gas Safety CP12 Endpoints ---
@router.post("/gas-safety/create", response_model=GasSafetyResponse)
def create_gas_safety_certificate(data: GasSafetyCreate, user=Depends(get_current_user)):
    cert_id = generate_id()
    cert_number = generate_certificate_number("CP12")
    now = datetime.now().isoformat()

    cert = {
        "id": cert_id,
        "certificate_number": cert_number,
        "customer_id": data.customer_id,
        "property_address": data.property_address,
        "property_type": data.property_type.value,
        "boiler_make": data.boiler_make,
        "boiler_model": data.boiler_model,
        "boiler_type": data.boiler_type.value,
        "boiler_location": data.boiler_location,
        "flue_type": data.flue_type.value,
        "gas_supply_condition": data.gas_supply_condition.value,
        "ventilation_condition": data.ventilation_condition.value,
        "safety_test_results": [t.dict() for t in data.safety_test_results],
        "gas_safe_registered_number": data.gas_safe_registered_number,
        "next_check_date": data.next_check_date,
        "status": get_status(data.next_check_date),
        "created_at": now,
    }
    gas_safety_certificates[cert_id] = cert
    return GasSafetyResponse(**cert)

@router.get("/gas-safety/list")
def list_gas_safety_certificates(
    status: Optional[str] = Query(None),
    property_address: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    results = list(gas_safety_certificates.values())
    if status:
        results = [c for c in results if c["status"] == status]
    if property_address:
        results = [c for c in results if property_address.lower() in c["property_address"].lower()]
    return results

@router.get("/gas-safety/expiring")
def get_expiring_gas_safety(user=Depends(get_current_user)):
    now = datetime.now()
    threshold = now + timedelta(days=365)
    results = []
    for cert in gas_safety_certificates.values():
        next_date = datetime.strptime(cert["next_check_date"], "%Y-%m-%d")
        if now <= next_date <= threshold:
            results.append(cert)
    return results

@router.get("/gas-safety/{cert_id}", response_model=GasSafetyResponse)
def get_gas_safety_certificate(cert_id: str, user=Depends(get_current_user)):
    if cert_id not in gas_safety_certificates:
        raise HTTPException(status_code=404, detail="Gas Safety certificate not found")
    return GasSafetyResponse(**gas_safety_certificates[cert_id])

@router.post("/gas-safety/generate-pdf")
def generate_gas_safety_pdf(cert_id: str, user=Depends(get_current_user)):
    if cert_id not in gas_safety_certificates:
        raise HTTPException(status_code=404, detail="Gas Safety certificate not found")

    cert = gas_safety_certificates[cert_id]

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    tests = cert.get("safety_test_results", []) or []
    overall_pass = all(
        str(t.get("test_result", "")).strip().lower() == "pass" for t in tests
    ) if tests else True
    stamp_text = "PASS" if overall_pass else "FAIL"

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Gas Safety Certificate (CP12)", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Certificate Number: {cert['certificate_number']}", styles["Normal"]))
    story.append(Paragraph(f"Date Issued: {cert['created_at'][:10]}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Property Details", styles["Heading2"]))
    story.append(Paragraph(f"Address: {cert['property_address']}", styles["Normal"]))
    story.append(Paragraph(f"Type: {str(cert['property_type']).title()}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Boiler Details", styles["Heading2"]))
    story.append(Paragraph(f"Make: {cert['boiler_make']} / Model: {cert['boiler_model']}", styles["Normal"]))
    story.append(Paragraph(f"Type: {str(cert['boiler_type']).title()} / Location: {cert['boiler_location']}", styles["Normal"]))
    story.append(Paragraph(f"Flue Type: {str(cert['flue_type']).replace('_', ' ').title()}", styles["Normal"]))
    story.append(Paragraph(f"Gas Supply: {str(cert['gas_supply_condition']).title()} / Ventilation: {str(cert['ventilation_condition']).title()}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Appliance Test Results", styles["Heading2"]))
    table_data = [["#", "Appliance", "Result", "Defect Found", "Action Required"]]
    for i, test in enumerate(tests, 1):
        table_data.append([
            str(i),
            str(test.get("appliance", "")),
            str(test.get("test_result", "")),
            str(test.get("defect_found", "")),
            str(test.get("action_required", "")),
        ])
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Engineer Declaration", styles["Heading2"]))
    story.append(Paragraph(f"Gas Safe Registered No: {cert['gas_safe_registered_number']}", styles["Normal"]))
    story.append(Paragraph(f"Next Safety Check Due: {cert['next_check_date']}", styles["Normal"]))
    story.append(Paragraph(f"Date: {cert['created_at'][:10]}", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b><font size=18>Result: {stamp_text}</font></b>", styles["Normal"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("This certificate is valid for 12 months from the date of issue.", styles["Normal"]))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    response = {
        "certificate_number": cert["certificate_number"],
        "pdf_base64": pdf_b64,
        "filename": f"CP12-{cert['certificate_number']}.pdf",
    }
    try:
        if r2.is_configured():
            key = f"certificates/{cert['certificate_number']}.pdf"
            r2.upload_bytes(key, pdf_bytes, "application/pdf")
            response["file_url"] = r2.file_url(key)
    except Exception:
        pass
    return response
