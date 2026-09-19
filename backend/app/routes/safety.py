"""Lone worker safety routes for VoiceField (UK field service SaaS)."""
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/safety", tags=["safety"])

# ── In-memory stores (module level; production → database) ──────────────
# Check-ins keyed by user id -> list of check-in dicts (newest last).
CHECK_INS: dict[str, list[dict]] = {}
# Alerts keyed by alert id -> alert dict.
ALERTS: dict[str, dict] = {}
# Safety settings keyed by business key -> config dict.
SAFETY_SETTINGS: dict[str, dict] = {}

DEFAULT_SETTINGS: dict = {
    "check_in_interval_minutes": 60,
    "emergency_contacts": [],
    "escalate_after_missed": 2,
}


def _settings_for(key: str = "default") -> dict:
    if key not in SAFETY_SETTINGS:
        SAFETY_SETTINGS[key] = {
            "check_in_interval_minutes": DEFAULT_SETTINGS["check_in_interval_minutes"],
            "emergency_contacts": list(DEFAULT_SETTINGS["emergency_contacts"]),
            "escalate_after_missed": DEFAULT_SETTINGS["escalate_after_missed"],
        }
    return SAFETY_SETTINGS[key]


def _user_name(user) -> Optional[str]:
    return getattr(user, "full_name", None) or getattr(user, "email", None)


# ── Schemas ──────────────────────────────────────────────────────────────
class CheckInBody(BaseModel):
    job_id: Optional[str] = None
    latitude: float
    longitude: float
    note: Optional[str] = None


class PanicBody(BaseModel):
    latitude: float
    longitude: float
    job_id: Optional[str] = None
    message: Optional[str] = None


class ResolveBody(BaseModel):
    resolution_note: Optional[str] = None


class EmergencyContact(BaseModel):
    name: str
    phone: str
    relation: Optional[str] = None


class SafetySettingsUpdate(BaseModel):
    check_in_interval_minutes: Optional[int] = Field(default=None, ge=1)
    emergency_contacts: Optional[list[EmergencyContact]] = None
    escalate_after_missed: Optional[int] = Field(default=None, ge=1)


# ── Lone worker: check-in ────────────────────────────────────────────────
@router.post("/check-in")
async def check_in(
    data: CheckInBody,
    current_user=Depends(get_current_user),
):
    """Record a lone worker check-in."""
    settings = _settings_for("default")
    now = datetime.utcnow()
    interval = settings.get("check_in_interval_minutes", 60)
    check_in_id = str(uuid4())
    record = {
        "id": check_in_id,
        "user_id": str(current_user.id),
        "user_name": _user_name(current_user),
        "timestamp": now.isoformat(),
        "location": {"latitude": data.latitude, "longitude": data.longitude},
        "job_id": data.job_id,
        "note": data.note,
    }
    CHECK_INS.setdefault(str(current_user.id), []).append(record)
    next_due = now + timedelta(minutes=interval)
    return {
        "id": check_in_id,
        "next_check_in_due": next_due.isoformat(),
        "message": "Check-in recorded. Stay safe.",
    }


# ── Lone worker: status ──────────────────────────────────────────────────
@router.get("/status")
async def safety_status(current_user=Depends(get_current_user)):
    """Return the current user's safety state."""
    settings = _settings_for("default")
    interval = settings.get("check_in_interval_minutes", 60)
    history = CHECK_INS.get(str(current_user.id), [])
    last = history[-1] if history else None
    next_due = None
    overdue = False
    if last:
        try:
            last_ts = datetime.fromisoformat(last["timestamp"])
        except (ValueError, KeyError, TypeError):
            last_ts = datetime.utcnow()
        next_due_dt = last_ts + timedelta(minutes=interval)
        next_due = next_due_dt.isoformat()
        overdue = datetime.utcnow() > next_due_dt
    active_alert = any(
        a.get("user_id") == str(current_user.id) and a.get("status") == "active"
        for a in ALERTS.values()
    )
    return {
        "last_check_in": last,
        "next_due": next_due,
        "overdue": overdue,
        "active_alert": active_alert,
    }


# ── Lone worker: panic ───────────────────────────────────────────────────
@router.post("/panic")
async def panic_alert(
    data: PanicBody,
    current_user=Depends(get_current_user),
):
    """Raise a PANIC alert and (simulated) notify emergency contacts + manager."""
    alert_id = str(uuid4())
    now = datetime.utcnow()
    alert = {
        "id": alert_id,
        "type": "PANIC",
        "user_id": str(current_user.id),
        "user_name": _user_name(current_user),
        "timestamp": now.isoformat(),
        "location": {"latitude": data.latitude, "longitude": data.longitude},
        "job_id": data.job_id,
        "message": data.message,
        "status": "active",
    }
    ALERTS[alert_id] = alert
    # Simulated notification (production → SMS/push via notify service).
    notified = ["manager", "emergency_contact"]
    return {"alert_id": alert_id, "status": "active", "notified": notified}


# ── Alerts: list (manager view) ──────────────────────────────────────────
@router.get("/alerts")
async def list_alerts(
    status: Optional[str] = Query(default=None),
    current_user=Depends(get_current_user),
):
    """List safety alerts, optionally filtered by status."""
    alerts = list(ALERTS.values())
    if status is not None:
        alerts = [a for a in alerts if a.get("status") == status]
    return {"alerts": alerts}


# ── Alerts: resolve ──────────────────────────────────────────────────────
@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    data: ResolveBody,
    current_user=Depends(get_current_user),
):
    """Mark a safety alert as resolved."""
    alert = ALERTS.get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert["status"] = "resolved"
    alert["resolved_at"] = datetime.utcnow().isoformat()
    alert["resolved_by"] = str(current_user.id)
    alert["resolution_note"] = data.resolution_note
    return alert


# ── Settings ─────────────────────────────────────────────────────────────
@router.get("/settings")
async def get_safety_settings():
    """Return the business safety configuration."""
    return _settings_for("default")


@router.put("/settings")
async def update_safety_settings(data: SafetySettingsUpdate):
    """Update the business safety configuration (partial)."""
    config = _settings_for("default")
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "emergency_contacts" and value is not None:
            config[key] = [c if isinstance(c, dict) else dict(c) for c in value]
        else:
            config[key] = value
    return config
