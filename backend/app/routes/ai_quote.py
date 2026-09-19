import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from pydantic import BaseModel, Field
from app.core.database import get_db
from app.models.models import User, Business, Job, Quote, QuoteItem, Service, Material
from app.routes.auth import get_current_user
from app.services import llm

router = APIRouter(prefix="/api/ai-quote", tags=["ai-quote"])


# ─── Request / Response Models ───────────────────────────

class PropertyDetails(BaseModel):
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    property_age: Optional[str] = None
    has_gas: Optional[bool] = None
    has_electric: Optional[bool] = None


class QuoteGenerateRequest(BaseModel):
    description: str
    property_type: str = "domestic"
    urgency: str = "standard"
    property_details: Optional[PropertyDetails] = None


class QuoteLineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float
    type: str  # material, labour, other


class QuoteGenerateResponse(BaseModel):
    job_type: str
    estimated_duration_minutes: int
    line_items: List[QuoteLineItem]
    subtotal: float
    vat: float
    total: float
    confidence: float
    suggested_services: List[str]


class SimilarJob(BaseModel):
    title: str
    final_price: float
    duration_minutes: int
    materials_used: List[str]


class SimilarJobsResponse(BaseModel):
    similar_jobs: List[SimilarJob]


class UpsellSuggestion(BaseModel):
    title: str
    description: str
    price: float
    reason: str
    priority: str


class UpsellResponse(BaseModel):
    suggestions: List[UpsellSuggestion]


class QuoteTemplate(BaseModel):
    job_type: str
    name: str
    default_services: List[str]
    estimated_duration: int
    base_price_range: str


class TemplatesResponse(BaseModel):
    templates: List[QuoteTemplate]


# ─── Job Type Detection ──────────────────────────────────

JOB_TYPE_KEYWORDS = {
    "boiler_repair": ["boiler repair", "boiler broken", "boiler not working", "boiler fix", "boiler fault"],
    "boiler_service": ["boiler service", "boiler servicing", "annual boiler", "gas safety check", "boiler check"],
    "boiler_install": ["boiler install", "new boiler", "replace boiler", "boiler replacement", "boiler upgrade"],
    "leak_repair": ["leak", "leaking", "drip", "dripping", "water leak", "pipe leak", "burst pipe"],
    "radiator_repair": ["radiator repair", "radiator broken", "radiator not working", "radiator leak"],
    "radiator_install": ["new radiator", "radiator install", "replace radiator", "add radiator", "radiator replacement"],
    "electrical_repair": ["fuse", "tripping", "trip", "electric", "electrical", "power cut", "no power", "wiring", "socket", "switch"],
    "gas_safety": ["gas safety", "gas check", "gas certificate", "cp12", "gas inspection"],
    "drain_unblock": ["drain", "unblock", "blocked drain", "blocked toilet", "blocked sink", "sewage"],
    "bathroom_refit": ["bathroom", "bathroom refit", "bathroom renovate", "shower install", "bathroom fitting"],
    "kitchen_refit": ["kitchen", "kitchen refit", "kitchen renovate", "kitchen fitting"],
    "roofing_repair": ["roof", "roofing", "roof repair", "leaking roof", "tile", "slate"],
    "window_repair": ["window", "window repair", "double glazing", "condensation", "sealed unit"],
    "door_repair": ["door", "door repair", "lock", "locksmith", "front door", "composite door"],
    "plastering": ["plaster", "plastering", "render", "skim", "wall repair"],
    "painting": ["paint", "painting", "decorating", "paint job", "wall paint"],
    "carpentry": ["carpenter", "carpentry", "wood", "shelving", "wardrobe", "cupboard", "door frame"],
    "appliance_repair": ["appliance", "washing machine", "dishwasher", "oven", "tumble dryer", "fridge", "freezer"],
}

EMERGENCY_KEYWORDS = ["emergency", "urgent", "asap", "flood", "gas leak", "no heating", "no hot water", "burst"]

NON_JOB_KEYWORDS = ["council tax", "council tax band", "home insurance", "building regulations", "planning permission"]


def detect_job_type(description: str) -> tuple[str, float]:
    desc_lower = description.lower()

    for keyword in NON_JOB_KEYWORDS:
        if keyword in desc_lower:
            raise ValueError(f"'{description}' does not appear to be a field service job.")

    best_match = "general_repair"
    best_confidence = 0.3

    for job_type, keywords in JOB_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                confidence = 0.6 + (len(kw) / len(desc_lower)) * 0.4
                confidence = min(confidence, 0.95)
                if confidence > best_confidence:
                    best_match = job_type
                    best_confidence = confidence
                break

    return best_match, round(best_confidence, 2)


def is_emergency(description: str, urgency: str) -> bool:
    if urgency in ("urgent", "emergency"):
        return True
    desc_lower = description.lower()
    return any(kw in desc_lower for kw in EMERGENCY_KEYWORDS)


# ─── Estimate Helpers ─────────────────────────────────────

JOB_DURATIONS = {
    "boiler_repair": 120,
    "boiler_service": 90,
    "boiler_install": 300,
    "leak_repair": 90,
    "radiator_repair": 90,
    "radiator_install": 120,
    "electrical_repair": 90,
    "gas_safety": 60,
    "drain_unblock": 90,
    "bathroom_refit": 480,
    "kitchen_refit": 600,
    "roofing_repair": 240,
    "window_repair": 120,
    "door_repair": 120,
    "plastering": 240,
    "painting": 240,
    "carpentry": 180,
    "appliance_repair": 90,
    "general_repair": 120,
}

LABOUR_RATES = {
    "standard": 45.0,
    "urgent": 55.0,
    "emergency": 70.0,
}

COMMON_MATERIALS = {
    "boiler_repair": [
        {"name": "Boiler valve", "price": 35.0},
        {"name": "Pressure sensor", "price": 45.0},
        {"name": "Ignition electrode", "price": 25.0},
    ],
    "boiler_service": [
        {"name": "Cleaning fluid", "price": 12.0},
        {"name": "Seal kit", "price": 18.0},
    ],
    "boiler_install": [
        {"name": "Boiler unit (mid-range)", "price": 850.0},
        {"name": "Flue kit", "price": 95.0},
        {"name": "Copper pipe & fittings", "price": 65.0},
        {"name": "Magnetic filter", "price": 85.0},
    ],
    "leak_repair": [
        {"name": "Pipe fittings", "price": 15.0},
        {"name": "PTFE tape", "price": 3.0},
        {"name": "Joint compound", "price": 8.0},
    ],
    "radiator_repair": [
        {"name": "Radiator valve", "price": 28.0},
        {"name": "Bleed key", "price": 2.0},
    ],
    "radiator_install": [
        {"name": "Radiator (double panel)", "price": 180.0},
        {"name": "Radiator valves x2", "price": 45.0},
        {"name": "Copper pipe & fittings", "price": 35.0},
    ],
    "electrical_repair": [
        {"name": "MCB breaker", "price": 18.0},
        {"name": "RCD breaker", "price": 42.0},
        {"name": "Socket outlet", "price": 12.0},
        {"name": "Junction box", "price": 8.0},
    ],
    "drain_unblock": [
        {"name": "Drain rod set", "price": 25.0},
        {"name": "Chemical drain cleaner", "price": 10.0},
    ],
    "door_repair": [
        {"name": "Lock mechanism", "price": 55.0},
        {"name": "Door handle", "price": 35.0},
    ],
    "window_repair": [
        {"name": "Sealed unit (standard)", "price": 85.0},
        {"name": "Window handle", "price": 18.0},
    ],
    "appliance_repair": [
        {"name": "Belt (washing machine)", "price": 22.0},
        {"name": "Pump (washing machine)", "price": 45.0},
    ],
}


def estimate_line_items(job_type: str, urgency: str) -> tuple[List[QuoteLineItem], float, float]:
    labour_rate = LABOUR_RATES.get(urgency, LABOUR_RATES["standard"])
    duration = JOB_DURATIONS.get(job_type, 120)
    labour_hours = duration / 60.0

    line_items: List[QuoteLineItem] = []

    # Labour
    labour_cost = round(labour_rate * labour_hours, 2)
    line_items.append(QuoteLineItem(
        description=f"Labour ({urgency.title()} rate)",
        quantity=labour_hours,
        unit_price=labour_rate,
        total=labour_cost,
        type="labour",
    ))

    # Materials
    materials_total = 0.0
    for mat in COMMON_MATERIALS.get(job_type, []):
        qty = 1
        item_total = round(mat["price"] * qty, 2)
        materials_total += item_total
        line_items.append(QuoteLineItem(
            description=mat["name"],
            quantity=qty,
            unit_price=mat["price"],
            total=item_total,
            type="material",
        ))

    subtotal = round(labour_cost + materials_total, 2)
    return line_items, subtotal, labour_cost


def apply_urgency_markup(subtotal: float, urgency: str) -> float:
    multipliers = {"standard": 1.0, "urgent": 1.25, "emergency": 1.5}
    return round(subtotal * multipliers.get(urgency, 1.0), 2)


def _parse_upsell_price(value) -> float:
    try:
        if isinstance(value, (int, float)):
            return round(float(value), 2)
        if isinstance(value, str):
            nums = re.findall(r"\d+(?:\.\d+)?", value.replace(",", ""))
            if not nums:
                return 0.0
            floats = [float(n) for n in nums]
            if len(floats) >= 2:
                return round(sum(floats) / len(floats), 2)
            return round(floats[0], 2)
    except (TypeError, ValueError):
        pass
    return 0.0


# ─── Upsell Logic ─────────────────────────────────────────

UPSELL_RULES = {
    "boiler_repair": [
        {"title": "Annual Boiler Service", "desc": "Prevent breakdowns with yearly servicing", "price": 95, "reason": "Reduces future breakdown risk by 80%", "priority": "high"},
        {"title": "Magnetic Filter Install", "desc": "Protects your boiler from sludge buildup", "price": 145, "reason": "Extends boiler life by 3-5 years", "priority": "medium"},
        {"title": "Smart Thermostat", "desc": "Save up to 30% on heating bills", "price": 220, "reason": "Complements boiler repair for efficiency", "priority": "medium"},
    ],
    "boiler_service": [
        {"title": "Powerflush", "desc": "Deep clean your central heating system", "price": 380, "reason": "Improves heating efficiency by 25%", "priority": "high"},
        {"title": "Radiator Upgrade", "desc": "Replace old radiators with efficient models", "price": 200, "reason": "Better heat distribution", "priority": "low"},
    ],
    "leak_repair": [
        {"title": "Pipe Insulation", "desc": "Prevent future frost damage to pipes", "price": 85, "reason": "Avoids costly freeze-burst repairs", "priority": "high"},
        {"title": "Stopcock Replacement", "desc": "Ensure you can shut off water in emergency", "price": 95, "reason": "Critical safety upgrade", "priority": "medium"},
    ],
    "electrical_repair": [
        {"title": "EICR (Electrical Certificate)", "desc": "Full electrical safety inspection", "price": 180, "reason": "Required for landlords, recommended every 5 years", "priority": "high"},
        {"title": "Consumer Unit Upgrade", "desc": "Modern fuse board with RCD protection", "price": 350, "reason": "Enhances safety significantly", "priority": "medium"},
    ],
    "radiator_repair": [
        {"title": "Magnetic Filter Install", "desc": "Prevents sludge buildup in heating system", "price": 145, "reason": "Reduces future radiator issues", "priority": "high"},
        {"title": "TRV Upgrade", "desc": "Thermostatic radiator valves for better control", "price": 65, "reason": "Saves energy and improves comfort", "priority": "low"},
    ],
}

AGE_BASED_UPSELLS = {
    "30+ years": [
        {"title": "Full Repipe", "desc": "Replace aging pipework for reliability", "price": 2500, "reason": "Old pipes are a major failure risk", "priority": "medium"},
    ],
    "20-30 years": [
        {"title": "Boiler Upgrade", "desc": "Modern A-rated condensing boiler", "price": 1800, "reason": "Older boilers are inefficient and unreliable", "priority": "medium"},
    ],
    "0-10 years": [
        {"title": "Smart Home Package", "desc": "Smart thermostat and TRVs for efficiency", "price": 320, "reason": "Newer property suits smart tech", "priority": "low"},
    ],
}


# ─── Endpoints ────────────────────────────────────────────

@router.post("/generate", response_model=QuoteGenerateResponse)
async def generate_quote(
    data: QuoteGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    if data.urgency not in ("standard", "urgent", "emergency"):
        raise HTTPException(status_code=400, detail="Invalid urgency. Must be standard, urgent, or emergency.")
    if data.property_type not in ("domestic", "commercial"):
        raise HTTPException(status_code=400, detail="Invalid property_type. Must be domestic or commercial.")

    try:
        job_type, confidence = detect_job_type(data.description)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # ─── Central LLM override (heuristic fallback) ───
    llm_duration_override: Optional[int] = None
    llm_services_override: Optional[List[str]] = None
    if llm.is_configured():
        try:
            known_slugs = sorted(set(JOB_TYPE_KEYWORDS) | {"general_repair"})
            prop = data.property_details.model_dump() if data.property_details else {}
            llm_prompt = (
                "You are a UK trades quoting assistant. Classify the job described below.\n"
                f"Description: {data.description}\n"
                f"Property type: {data.property_type}\n"
                f"Property details: {prop}\n"
                f"Known job-type slugs: {known_slugs}\n"
                "Return ONLY valid JSON with keys: "
                '{"job_type": str (one of the known job-type slugs), "confidence": float 0-1, '
                '"scope_notes": str, "suggested_services": [str], "estimated_duration_minutes": int}. '
                "Use UK English."
            )
            llm_system = "You classify UK field-service jobs. Reply with valid JSON only, no markdown."
            llm_result = await llm.complete_json(llm_prompt, system=llm_system, max_tokens=800, temperature=0.2)
            cand = str(llm_result.get("job_type", "") or "").strip()
            try:
                cand_conf = float(llm_result.get("confidence", 0) or 0)
            except (TypeError, ValueError):
                cand_conf = 0.0
            if cand in set(JOB_TYPE_KEYWORDS) | {"general_repair"} and cand_conf >= 0.5:
                job_type = cand
                confidence = round(min(max(cand_conf, 0.0), 1.0), 2)
                dur = llm_result.get("estimated_duration_minutes")
                try:
                    dur_int = int(dur)  # type: ignore[arg-type]
                    if 15 <= dur_int <= 5000:
                        llm_duration_override = dur_int
                except (TypeError, ValueError):
                    pass
                sugg = llm_result.get("suggested_services")
                if isinstance(sugg, list):
                    cleaned = [str(s).strip() for s in sugg if str(s).strip()]
                    if cleaned:
                        llm_services_override = cleaned
        except Exception:
            pass

    urgent = is_emergency(data.description, data.urgency)
    if urgent and data.urgency == "standard":
        data.urgency = "urgent"
        confidence = max(confidence - 0.05, 0.1)

    duration = llm_duration_override if llm_duration_override is not None else JOB_DURATIONS.get(job_type, 120)
    if data.property_type == "commercial":
        duration = int(duration * 1.4)

    line_items, subtotal, labour_cost = estimate_line_items(job_type, data.urgency)
    marked_up = apply_urgency_markup(subtotal, data.urgency)
    vat = round(marked_up * 0.20, 2)
    total = round(marked_up + vat, 2)

    suggested_services = []
    if llm_services_override is not None:
        suggested_services = llm_services_override
    else:
        for rule in UPSELL_RULES.get(job_type, []):
            suggested_services.append(rule["title"])

    return QuoteGenerateResponse(
        job_type=job_type,
        estimated_duration_minutes=duration,
        line_items=line_items,
        subtotal=marked_up,
        vat=vat,
        total=total,
        confidence=confidence,
        suggested_services=suggested_services,
    )


@router.post("/similar", response_model=SimilarJobsResponse)
async def find_similar_jobs(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    description = data.get("description", "")
    business_id_result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = business_id_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    try:
        target_job_type, _ = detect_job_type(description)
    except ValueError:
        target_job_type = "general_repair"

    result = await db.execute(
        select(Job)
        .where(Job.business_id == business.id, Job.status == "completed")
        .order_by(Job.created_at.desc())
        .limit(50)
    )
    completed_jobs = result.scalars().all()

    similar = []
    for job in completed_jobs:
        if job.estimated_cost and job.estimated_cost > 0:
            duration = 0
            if job.started_at and job.completed_at:
                delta = job.completed_at - job.started_at
                duration = int(delta.total_seconds() / 60)

            similar.append(SimilarJob(
                title=job.title or "Completed job",
                final_price=float(job.final_cost or job.estimated_cost),
                duration_minutes=duration or 120,
                materials_used=[],
            ))

    similar.sort(key=lambda x: x.final_price, reverse=True)
    return SimilarJobsResponse(similar_jobs=similar[:10])


@router.post("/upsell", response_model=UpsellResponse)
async def get_upsell_suggestions(
    data: dict,
    current_user: User = Depends(get_current_user),
):
    job_type = data.get("job_type", "general_repair")
    customer_history = data.get("customer_history", False)
    property_age = data.get("property_age", "")

    suggestions: List[UpsellSuggestion] = []

    for rule in UPSELL_RULES.get(job_type, []):
        suggestions.append(UpsellSuggestion(
            title=rule["title"],
            description=rule["desc"],
            price=rule["price"],
            reason=rule["reason"],
            priority=rule["priority"],
        ))

    for age_range, upsells in AGE_BASED_UPSELLS.items():
        if property_age and any(a in property_age for a in age_range.split()):
            for upsell in upsells:
                suggestions.append(UpsellSuggestion(
                    title=upsell["title"],
                    description=upsell["desc"],
                    price=upsell["price"],
                    reason=upsell["reason"],
                    priority=upsell["priority"],
                ))

    if customer_history:
        suggestions.append(UpsellSuggestion(
            title="Maintenance Contract",
            description="Annual maintenance agreement with priority service",
            price=299,
            reason="Returning customer - loyalty incentive",
            priority="high",
        ))

    # ─── Central LLM merge (heuristic fallback, never 500) ───
    if llm.is_configured():
        try:
            description = str(data.get("description", "") or "")
            llm_prompt = (
                "You are a UK trades upsell assistant. Suggest relevant additional services.\n"
                f"Job type: {job_type}\n"
                f"Description: {description}\n"
                f"Property age: {property_age}\n"
                "Return ONLY valid JSON with key "
                '"suggestions": [{title: str, description: str, price_range: str, priority: str (high|medium|low), reason: str}]. '
                "Use UK English."
            )
            llm_system = "You suggest UK field-service upsells. Reply with valid JSON only, no markdown."
            llm_result = await llm.complete_json(llm_prompt, system=llm_system, max_tokens=1000, temperature=0.3)
            raw_sugs = llm_result.get("suggestions", [])
            if isinstance(raw_sugs, list):
                existing_titles = {s.title.strip().lower() for s in suggestions}
                for item in raw_sugs:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title", "") or "").strip()
                    if not title or title.lower() in existing_titles:
                        continue
                    desc = str(item.get("description", "") or "").strip() or title
                    reason = str(item.get("reason", "") or "").strip() or "Suggested for this job"
                    priority = str(item.get("priority", "") or "").strip().lower() or "medium"
                    if priority not in ("high", "medium", "low"):
                        priority = "medium"
                    price_raw = item.get("price", item.get("price_range", 0))
                    price_val = _parse_upsell_price(price_raw)
                    suggestions.append(UpsellSuggestion(
                        title=title,
                        description=desc,
                        price=price_val,
                        reason=reason,
                        priority=priority,
                    ))
                    existing_titles.add(title.lower())
        except Exception:
            pass

    priority_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda x: priority_order.get(x.priority, 99))

    return UpsellResponse(suggestions=suggestions[:8])


@router.get("/templates", response_model=TemplatesResponse)
async def get_templates(
    current_user: User = Depends(get_current_user),
):
    templates = [
        QuoteTemplate(
            job_type="boiler_repair",
            name="Boiler Repair",
            default_services=["Boiler diagnostic", "Component repair/replacement", "System pressure check", "Flue inspection"],
            estimated_duration=120,
            base_price_range="£150 - £450",
        ),
        QuoteTemplate(
            job_type="boiler_service",
            name="Annual Boiler Service",
            default_services=["Boiler inspection", "Combustion analysis", "Safety check", "System flush"],
            estimated_duration=90,
            base_price_range="£75 - £120",
        ),
        QuoteTemplate(
            job_type="boiler_install",
            name="Boiler Installation",
            default_services=["Old boiler removal", "New boiler install", "Flue fitting", "System powerflush", "Commissioning"],
            estimated_duration=300,
            base_price_range="£1,800 - £3,500",
        ),
        QuoteTemplate(
            job_type="leak_repair",
            name="Leak Repair",
            default_services=["Leak detection", "Pipe repair/replacement", "Pressure test", "Area make-good"],
            estimated_duration=90,
            base_price_range="£80 - £350",
        ),
        QuoteTemplate(
            job_type="electrical_repair",
            name="Electrical Repair",
            default_services=["Fault diagnosis", "Repair/replacement", "Testing & certification"],
            estimated_duration=90,
            base_price_range="£80 - £250",
        ),
        QuoteTemplate(
            job_type="drain_unblock",
            name="Drain Unblocking",
            default_services=["CCTV inspection", "High-pressure jetting", "Root removal", "Patch repair"],
            estimated_duration=90,
            base_price_range="£100 - £300",
        ),
        QuoteTemplate(
            job_type="radiator_install",
            name="Radiator Installation",
            default_services=["Old radiator removal", "New radiator fitting", "Pipe connection", "System balance"],
            estimated_duration=120,
            base_price_range="£150 - £400",
        ),
        QuoteTemplate(
            job_type="gas_safety",
            name="Gas Safety Certificate",
            default_services=["Gas appliance check", "Flue & ventilation test", "Gas pipework inspection", "CP12 certificate issued"],
            estimated_duration=60,
            base_price_range="£60 - £90",
        ),
    ]

    return TemplatesResponse(templates=templates)
