from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from app.routes.auth import get_current_user
from app.models.models import User

router = APIRouter(prefix="/api/pricebook", tags=["pricebook"])


class ServiceCreate(BaseModel):
    name: str
    category: str
    description: Optional[str] = None
    base_price: float
    unit: str = "fixed"
    estimated_duration_minutes: Optional[float] = None
    vat_rate: float = 20.0


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    base_price: Optional[float] = None
    unit: Optional[str] = None
    estimated_duration_minutes: Optional[float] = None
    vat_rate: Optional[float] = None


class MaterialCreate(BaseModel):
    name: str
    sku: str
    category: str
    unit_price: float
    unit: str = "each"
    supplier: Optional[str] = None
    markup_percent: float = 0.0


class MaterialUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    unit_price: Optional[float] = None
    unit: Optional[str] = None
    supplier: Optional[str] = None
    markup_percent: Optional[float] = None


class MarkupRules(BaseModel):
    default_markup: float = 30.0
    emergency_markup: float = 50.0
    weekend_markup: float = 25.0


class QuoteTemplate(BaseModel):
    includes_vat: bool = True
    payment_terms: str = "Net 30"
    valid_days: int = 30
    terms_text: str = (
        "This quote is valid for the period stated above. "
        "Prices include VAT unless otherwise stated. "
        "Payment is due within the terms specified. "
        "Work not commenced may be subject to price revision."
    )


class CalcServiceItem(BaseModel):
    id: str
    quantity: float = 1.0


class CalcMaterialItem(BaseModel):
    id: str
    quantity: float = 1.0


class PriceCalculation(BaseModel):
    services: List[CalcServiceItem]
    materials: List[CalcMaterialItem]
    markup_override: Optional[float] = None
    job_type: str = "standard"


class PriceResult(BaseModel):
    subtotal: float
    materials_cost: float
    labour_cost: float
    markup_amount: float
    vat_amount: float
    total: float


# In-memory stores
services_db: dict[str, dict] = {}
materials_db: dict[str, dict] = {}
markup_rules = MarkupRules()
quote_template = QuoteTemplate()


def _apply_updates(item: dict, updates: dict) -> dict:
    for k, v in updates.items():
        if v is not None:
            item[k] = v
    return item


@router.post("/services")
def create_service(data: ServiceCreate, current_user: User = Depends(get_current_user)):
    service_id = str(uuid4())
    service = {
        "id": service_id,
        "name": data.name,
        "category": data.category,
        "description": data.description,
        "base_price": data.base_price,
        "unit": data.unit,
        "estimated_duration_minutes": data.estimated_duration_minutes,
        "vat_rate": data.vat_rate,
        "created_by": str(current_user.id),
    }
    services_db[service_id] = service
    return service


@router.get("/services")
def list_services(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    items = list(services_db.values())
    if category:
        items = [s for s in items if s["category"].lower() == category.lower()]
    return items


@router.put("/services/{service_id}")
def update_service(
    service_id: str,
    data: ServiceUpdate,
    current_user: User = Depends(get_current_user),
):
    if service_id not in services_db:
        raise HTTPException(status_code=404, detail="Service not found")
    services_db[service_id] = _apply_updates(services_db[service_id], data.model_dump())
    return services_db[service_id]


@router.delete("/services/{service_id}")
def delete_service(service_id: str, current_user: User = Depends(get_current_user)):
    if service_id not in services_db:
        raise HTTPException(status_code=404, detail="Service not found")
    del services_db[service_id]
    return {"message": "Service deleted"}


@router.post("/materials")
def create_material(data: MaterialCreate, current_user: User = Depends(get_current_user)):
    material_id = str(uuid4())
    material = {
        "id": material_id,
        "name": data.name,
        "sku": data.sku,
        "category": data.category,
        "unit_price": data.unit_price,
        "unit": data.unit,
        "supplier": data.supplier,
        "markup_percent": data.markup_percent,
        "created_by": str(current_user.id),
    }
    materials_db[material_id] = material
    return material


@router.get("/materials")
def list_materials(current_user: User = Depends(get_current_user)):
    return list(materials_db.values())


@router.put("/materials/{material_id}")
def update_material(
    material_id: str,
    data: MaterialUpdate,
    current_user: User = Depends(get_current_user),
):
    if material_id not in materials_db:
        raise HTTPException(status_code=404, detail="Material not found")
    materials_db[material_id] = _apply_updates(materials_db[material_id], data.model_dump())
    return materials_db[material_id]


@router.get("/markups")
def get_markups(current_user: User = Depends(get_current_user)):
    return markup_rules.model_dump()


@router.post("/markups")
def update_markups(data: MarkupRules, current_user: User = Depends(get_current_user)):
    global markup_rules
    markup_rules = data
    return markup_rules.model_dump()


@router.get("/quote-template")
def get_quote_template(current_user: User = Depends(get_current_user)):
    return quote_template.model_dump()


@router.post("/quote-template")
def update_quote_template(data: QuoteTemplate, current_user: User = Depends(get_current_user)):
    global quote_template
    quote_template = data
    return quote_template.model_dump()


@router.post("/calculate", response_model=PriceResult)
def calculate_price(data: PriceCalculation, current_user: User = Depends(get_current_user)):
    labour_cost = 0.0
    for item in data.services:
        svc = services_db.get(item.id)
        if not svc:
            raise HTTPException(status_code=404, detail=f"Service {item.id} not found")
        labour_cost += svc["base_price"] * item.quantity

    materials_cost = 0.0
    for item in data.materials:
        mat = materials_db.get(item.id)
        if not mat:
            raise HTTPException(status_code=404, detail=f"Material {item.id} not found")
        price_with_markup = mat["unit_price"] * (1 + mat["markup_percent"] / 100)
        materials_cost += price_with_markup * item.quantity

    subtotal = labour_cost + materials_cost

    if data.markup_override is not None:
        markup_pct = data.markup_override
    elif data.job_type == "emergency":
        markup_pct = markup_rules.emergency_markup
    elif data.job_type == "weekend":
        markup_pct = markup_rules.weekend_markup
    else:
        markup_pct = markup_rules.default_markup

    markup_amount = subtotal * (markup_pct / 100)
    total_before_vat = subtotal + markup_amount

    vat_amount = 0.0
    if quote_template.includes_vat:
        for item in data.services:
            svc = services_db.get(item.id)
            if svc:
                vat_amount += svc["base_price"] * item.quantity * (svc["vat_rate"] / 100)

    total = total_before_vat + vat_amount

    return PriceResult(
        subtotal=round(subtotal, 2),
        materials_cost=round(materials_cost, 2),
        labour_cost=round(labour_cost, 2),
        markup_amount=round(markup_amount, 2),
        vat_amount=round(vat_amount, 2),
        total=round(total, 2),
    )
