"""RAMS — risk assessments + method statements for site work."""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from uuid import uuid4
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/rams", tags=["rams"])

# In-memory store (production → DB table). Templates are static UK trade RAMS.
TEMPLATES: dict[str, dict] = {
    "general_site": {
        "id": "general_site", "name": "General Site Work", "trade": "All trades",
        "items": [
            {"id": "asbestos", "label": "Checked for asbestos risk before disturbing fabric", "kind": "check", "required": True, "hint": "If in doubt, stop and arrange a survey"},
            {"id": "electrics", "label": "Electrics isolated where working near wiring", "kind": "check", "required": True, "hint": ""},
            {"id": "access", "label": "Safe access in place (loft boards, ladders footed)", "kind": "check", "required": True, "hint": ""},
            {"id": "dust", "label": "Dust control (extraction/sheets) arranged", "kind": "check", "required": False, "hint": ""},
            {"id": "waste", "label": "Waste removal plan confirmed with customer", "kind": "check", "required": False, "hint": ""},
            {"id": "notes", "label": "Site-specific notes", "kind": "text", "required": False, "hint": "Anything unusual about this property"},
        ],
    },
    "gas_work": {
        "id": "gas_work", "name": "Gas Work", "trade": "Gas engineers",
        "items": [
            {"id": "gassafe", "label": "Gas Safe card on person and in date", "kind": "check", "required": True, "hint": "No card = no gas work"},
            {"id": "flue", "label": "Flue integrity visually confirmed", "kind": "check", "required": True, "hint": ""},
            {"id": "ventilation", "label": "Ventilation adequate for appliance", "kind": "check", "required": True, "hint": ""},
            {"id": "tightness", "label": "Tightness test to be performed after work", "kind": "check", "required": True, "hint": ""},
            {"id": "co_alarm", "label": "CO alarm present/working (advise if missing)", "kind": "check", "required": False, "hint": ""},
            {"id": "notes", "label": "Site-specific notes", "kind": "text", "required": False, "hint": ""},
        ],
    },
    "electrical": {
        "id": "electrical", "name": "Electrical Work", "trade": "Electricians",
        "items": [
            {"id": "isolation", "label": "Safe isolation performed and proved dead", "kind": "check", "required": True, "hint": "Test before touch, every time"},
            {"id": "lockoff", "label": "Lock-off kit applied with warning notice", "kind": "check", "required": True, "hint": ""},
            {"id": "rcd", "label": "RCD protection confirmed for circuits worked on", "kind": "check", "required": False, "hint": ""},
            {"id": "livework", "label": "Live-work justification (only if unavoidable)", "kind": "text", "required": False, "hint": "Leave blank if no live work"},
            {"id": "notes", "label": "Site-specific notes", "kind": "text", "required": False, "hint": ""},
        ],
    },
}

ASSESSMENTS: dict[str, dict] = {}


@router.get("/templates")
async def list_templates(current_user=Depends(get_current_user)):
    return {"templates": list(TEMPLATES.values())}


@router.post("/assessments")
async def create_assessment(data: dict, current_user=Depends(get_current_user)):
    template = TEMPLATES.get(str(data.get("template_id", "")))
    if not template:
        raise HTTPException(status_code=404, detail="Unknown template")
    answers = {a.get("item_id"): a for a in (data.get("answers") or []) if isinstance(a, dict)}
    failed = [it["id"] for it in template["items"]
              if it["required"] and not (answers.get(it["id"]) or {}).get("checked")]
    aid = str(uuid4())
    ASSESSMENTS[aid] = {
        "id": aid,
        "job_id": data.get("job_id"),
        "template_id": template["id"],
        "template_name": template["name"],
        "answers": data.get("answers") or [],
        "engineer_name": data.get("engineer_name", ""),
        "signed": bool(data.get("signature_base64")),
        "created_at": datetime.utcnow().isoformat(),
        "created_by": str(current_user.id),
    }
    return {"id": aid, "passed": len(failed) == 0, "failed_items": failed}


@router.get("/assessments")
async def list_assessments(job_id: str = "", current_user=Depends(get_current_user)):
    items = [a for a in ASSESSMENTS.values()
             if not job_id or a.get("job_id") == job_id]
    items.sort(key=lambda a: a["created_at"], reverse=True)
    out = []
    for a in items:
        tpl = TEMPLATES.get(a["template_id"], {})
        labels = {it["id"]: it["label"] for it in tpl.get("items", [])}
        out.append({**a, "labels": labels})
    return {"assessments": out}


@router.get("/assessments/{assessment_id}")
async def get_assessment(assessment_id: str, current_user=Depends(get_current_user)):
    a = ASSESSMENTS.get(assessment_id)
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")
    tpl = TEMPLATES.get(a["template_id"], {})
    labels = {it["id"]: it["label"] for it in tpl.get("items", [])}
    return {**a, "labels": labels}
