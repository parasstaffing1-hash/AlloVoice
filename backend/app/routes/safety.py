"""Lone worker safety routes for VoiceField (UK field service SaaS)."""
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.routes.auth import get_current_user

try:
    # Reuse the real Twilio sender - never reimplement Twilio in this module.
    from app.routes.sms import send_sms
except Exception:  # pragma: no cover - safety router must load even if sms breaks
    send_sms = None  # type: ignore

router = APIRouter(prefix="/api/safety", tags=["safety"])

# ── In-memory stores (module level; production → database) ──────────────
# Check-ins keyed by user id -> list of check-in dicts (newest last).
CHECK_INS: dict[str, list[dict]] = {}
# Alerts keyed by alert id -> alert dict.
ALERTS: dict[str, dict] = {}
# Safety settings keyed by business key -> config dict.
# Keys:
#   "default"   -> global fallback shared by everyone (backward compatible).
#   "user:{id}" -> per-user override. When a user id is provided (via the
#                  ?user_id= query param on /settings, or via the
#                  authenticated user id in check-in/status/panic), the
#                  per-user key is used. If it does not exist yet it is
#                  initialised as a copy of the current global "default"
#                  (falling back to DEFAULT_SETTINGS), so different engineers
#                  can have different emergency contacts / intervals without
#                  affecting each other.
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


def _user_settings_key(user_id: Optional[str]) -> str:
    """Map a user id to its per-user settings key (fallback: global default)."""
    if user_id:
        return f"user:{user_id}"
    return "default"


def _effective_settings(user_id: Optional[str] = None) -> dict:
    """Return the settings that apply to a user.

    Per-user overrides (key ``user:{id}``) win when a user id is given;
    otherwise the global ``"default"`` is returned. A missing per-user entry
    is initialised as a copy of the current global default (falling back to
    DEFAULT_SETTINGS) so global defaults keep propagating to new users.
    Contact dicts are copied so edits never leak across users.
    """
    if not user_id:
        return _settings_for("default")
    key = _user_settings_key(user_id)
    if key not in SAFETY_SETTINGS:
        base = SAFETY_SETTINGS.get("default", DEFAULT_SETTINGS)
        SAFETY_SETTINGS[key] = {
            "check_in_interval_minutes": base.get(
                "check_in_interval_minutes",
                DEFAULT_SETTINGS["check_in_interval_minutes"],
            ),
            "emergency_contacts": [
                dict(c) if isinstance(c, dict) else c
                for c in base.get("emergency_contacts", [])
            ],
            "escalate_after_missed": base.get(
                "escalate_after_missed", DEFAULT_SETTINGS["escalate_after_missed"]
            ),
        }
    return SAFETY_SETTINGS[key]


def _user_name(user) -> Optional[str]:
    return getattr(user, "full_name", None) or getattr(user, "email", None)


def _user_phone(user) -> str:
    return getattr(user, "phone", None) or "no phone on file"


def _build_panic_message(
    user_name: str,
    user_phone: str,
    when_iso: str,
    latitude: float,
    longitude: float,
    job_id: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    """Build the PANIC SMS body. Never raises on missing optionals."""
    parts = [f"PANIC ALERT from {user_name} ({user_phone}) at {when_iso}."]
    parts.append(f"Location: lat {latitude}, lng {longitude}.")
    if job_id:
        parts.append(f"Job: {job_id}.")
    if note:
        parts.append(f"Note: {note}")
    parts.append("Call them immediately.")
    return " ".join(parts)


async def _resolve_manager_contact(current_user, db) -> Optional[dict]:
    """Best-effort manager lookup. Never raises; returns None if unresolvable.

    Resolution order:
      1. Explicit manager attributes on the user object (forward-compatible
         if the User model ever gains manager_* fields).
      2. DB fallback: technician -> business -> business owner, treated as
         the manager. Skipped (returns None) when there is no db session,
         the user is not a technician, or the owner has no phone / is the
         user themselves.
    """
    try:
        mgr_phone = (
            getattr(current_user, "manager_phone", None)
            or getattr(current_user, "manager_mobile", None)
            or getattr(current_user, "manager_contact_phone", None)
        )
        if mgr_phone:
            mgr_name = (
                getattr(current_user, "manager_name", None)
                or getattr(current_user, "manager_full_name", None)
                or "manager"
            )
            return {"name": str(mgr_name), "phone": str(mgr_phone)}
        if db is not None:
            try:
                from app.models.models import Business, Technician, User as UserModel

                result = await db.execute(
                    select(Technician).where(Technician.user_id == current_user.id)
                )
                tech = result.scalar_one_or_none()
                business = None
                if tech is not None and getattr(tech, "business_id", None):
                    bres = await db.execute(
                        select(Business).where(Business.id == tech.business_id)
                    )
                    business = bres.scalar_one_or_none()
                if business is not None:
                    ores = await db.execute(
                        select(UserModel).where(UserModel.id == business.owner_id)
                    )
                    owner = ores.scalar_one_or_none()
                    if owner is not None and getattr(owner, "phone", None):
                        # Never SMS the panicking user as their own manager.
                        if str(owner.id) != str(current_user.id):
                            return {
                                "name": getattr(owner, "full_name", None)
                                or getattr(owner, "email", None)
                                or "manager",
                                "phone": owner.phone,
                            }
            except Exception:
                pass
    except Exception:
        pass
    return None


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
    # Per-user interval when the engineer has overrides, else global default.
    settings = _effective_settings(str(current_user.id))
    now = datetime.utcnow()
    interval = settings.get("check_in_interval_minutes", 60)
    if not isinstance(interval, (int, float)) or interval <= 0:
        interval = 60
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
    """Return the current user's safety state.

    In addition to ``overdue``, this reports ``escalation_due`` (True once
    the engineer has missed ``escalate_after_missed`` check-in intervals) and
    ``missed_by_minutes`` (whole minutes past the next-due time, 0 when not
    overdue) so the frontend can auto-prompt escalation. Computed here from
    ``last_check_in`` + interval - no extra endpoints.
    """
    # Per-user interval/threshold when the engineer has overrides.
    settings = _effective_settings(str(current_user.id))
    interval = settings.get("check_in_interval_minutes", 60)
    if not isinstance(interval, (int, float)) or interval <= 0:
        interval = 60
    escalate_after_missed = settings.get("escalate_after_missed", 2)
    if not isinstance(escalate_after_missed, (int, float)) or escalate_after_missed < 1:
        escalate_after_missed = 2
    history = CHECK_INS.get(str(current_user.id), [])
    last = history[-1] if history else None
    next_due = None
    overdue = False
    escalation_due = False
    missed_by_minutes = 0
    if last:
        try:
            last_ts = datetime.fromisoformat(last["timestamp"])
        except (ValueError, KeyError, TypeError):
            last_ts = datetime.utcnow()
        next_due_dt = last_ts + timedelta(minutes=interval)
        next_due = next_due_dt.isoformat()
        now = datetime.utcnow()
        overdue = now > next_due_dt
        if overdue:
            # Whole minutes past the due time (never negative).
            missed_by_minutes = max(
                0, int((now - next_due_dt).total_seconds() // 60)
            )
            # Escalate once `escalate_after_missed` full intervals elapsed
            # since the last check-in (e.g. 2 x 60min with defaults).
            try:
                elapsed_minutes = (now - last_ts).total_seconds() / 60
                missed_intervals = int(elapsed_minutes // interval)
                escalation_due = bool(missed_intervals >= escalate_after_missed)
            except Exception:
                # Fail-safe for safety code: if overdue but the maths failed,
                # still flag escalation rather than silently swallowing it.
                escalation_due = True
    active_alert = any(
        a.get("user_id") == str(current_user.id) and a.get("status") == "active"
        for a in ALERTS.values()
    )
    return {
        "last_check_in": last,
        "next_due": next_due,
        "overdue": overdue,
        "escalation_due": escalation_due,
        "missed_by_minutes": missed_by_minutes,
        "active_alert": active_alert,
    }


# ── Lone worker: panic ───────────────────────────────────────────────────
@router.post("/panic")
async def panic_alert(
    data: PanicBody,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Raise a PANIC alert and notify emergency contacts + manager via real SMS.

    The alert record is ALWAYS stored first - every failure path below
    degrades to a recorded alert, never an exception. Each SMS is sent and
    guarded individually so one bad number never blocks the others.
    """
    alert_id = str(uuid4())
    now = datetime.utcnow()
    user_name = _user_name(current_user) or "Unknown user"
    user_phone = _user_phone(current_user)
    alert = {
        "id": alert_id,
        "type": "PANIC",
        "user_id": str(current_user.id),
        "user_name": user_name,
        "timestamp": now.isoformat(),
        "location": {"latitude": data.latitude, "longitude": data.longitude},
        "job_id": data.job_id,
        "message": data.message,
        "status": "active",
    }
    # NEVER lose the alert: persist before any SMS work (SMS must not block it).
    ALERTS[alert_id] = alert

    # --- Real SMS notifications (best-effort; failures never lose the alert) ---
    notifications: list[dict] = []
    sms_available = True
    try:
        # Per-user emergency contacts when the engineer has overrides.
        settings = _effective_settings(str(current_user.id))
        contacts = settings.get("emergency_contacts", []) or []
        recipients: list[dict] = []
        for c in contacts:
            if isinstance(c, dict):
                name = c.get("name") or "emergency contact"
                phone = c.get("phone")
            else:
                name = getattr(c, "name", None) or "emergency contact"
                phone = getattr(c, "phone", None)
            recipients.append({"name": str(name), "phone": phone})
        # Plus the user's manager when resolvable (never raises).
        try:
            manager = await _resolve_manager_contact(current_user, db)
        except Exception:
            manager = None
        if manager and manager.get("phone"):
            recipients.append(
                {"name": manager.get("name") or "manager", "phone": manager.get("phone")}
            )

        if send_sms is None:
            # sms module failed to import: treat as SMS unavailable.
            sms_available = False
            for r in recipients:
                notifications.append(
                    {
                        "name": r.get("name"),
                        "phone": r.get("phone"),
                        "sent": False,
                        "error": "SMS sender unavailable",
                    }
                )
        else:
            message = _build_panic_message(
                user_name,
                user_phone,
                now.isoformat(),
                data.latitude,
                data.longitude,
                data.job_id,
                data.message,
            )
            for r in recipients:
                phone = r.get("phone")
                if not phone:
                    notifications.append(
                        {
                            "name": r.get("name"),
                            "phone": phone,
                            "sent": False,
                            "error": "missing phone number",
                        }
                    )
                    continue
                try:
                    result = await send_sms(
                        to_phone=phone,
                        message=message,
                        current_user=current_user,
                        db=db,
                    )
                    if isinstance(result, dict) and result.get("success"):
                        notifications.append(
                            {"name": r.get("name"), "phone": phone, "sent": True}
                        )
                    else:
                        err = "SMS send failed"
                        if isinstance(result, dict):
                            err = str(result.get("error") or err)
                        notifications.append(
                            {
                                "name": r.get("name"),
                                "phone": phone,
                                "sent": False,
                                "error": err[:300],
                            }
                        )
                except HTTPException as e:
                    # 503 = Twilio creds missing; 422 = bad number, etc.
                    # Either way: record it, keep notifying everyone else.
                    if e.status_code == 503:
                        sms_available = False
                    notifications.append(
                        {
                            "name": r.get("name"),
                            "phone": phone,
                            "sent": False,
                            "error": str(e.detail)[:300],
                        }
                    )
                except Exception as e:
                    notifications.append(
                        {
                            "name": r.get("name"),
                            "phone": phone,
                            "sent": False,
                            "error": str(e)[:300],
                        }
                    )
    except HTTPException as e:
        # Should already be handled per-contact above; belt-and-braces so the
        # endpoint never propagates 503/422 - the alert is already recorded.
        if e.status_code == 503:
            sms_available = False
    except Exception:
        # Safety code must never 500: degrade to the recorded alert.
        pass

    # Compat field: only contacts actually sent to (reflects reality, not intent).
    notified = [n["name"] for n in notifications if n.get("sent")]
    response: dict = {
        "alert_id": alert_id,
        "status": "active",
        "notified": notified,
        "notifications": notifications,
        "sms_available": sms_available,
    }
    if not sms_available:
        response["detail"] = (
            "Alert recorded but SMS not configured — call emergency contacts manually"
        )
    return response


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
async def get_safety_settings(user_id: Optional[str] = Query(default=None)):
    """Return the safety configuration.

    - Without ``?user_id=``: the global default (backward compatible).
    - With ``?user_id=<id>``: that engineer's per-user override
      (``user:{id}``), initialised from the global default on first use so
      different engineers can have different emergency contacts.
    """
    if user_id:
        return _effective_settings(user_id)
    return _settings_for("default")


@router.put("/settings")
async def update_safety_settings(
    data: SafetySettingsUpdate,
    user_id: Optional[str] = Query(default=None),
):
    """Update the safety configuration (partial).

    - Without ``?user_id=``: updates the global default (backward compatible).
    - With ``?user_id=<id>``: updates only that engineer's per-user override
      (``user:{id}``), leaving the global default and other engineers
      untouched.
    """
    config = _effective_settings(user_id) if user_id else _settings_for("default")
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "emergency_contacts" and value is not None:
            config[key] = [c if isinstance(c, dict) else dict(c) for c in value]
        else:
            config[key] = value
    return config
