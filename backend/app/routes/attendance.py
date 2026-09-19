"""Time & attendance for VoiceField (UK field service SaaS).

Times are ISO-8601 UTC (``datetime.utcnow().isoformat() + "Z"``); display in
Europe/London (en-GB) on the client. Overtime accrues after 8 hours worked
in a shift (480 minutes); breaks are unpaid and excluded from worked time.

Storage is in-memory (module level) dicts keyed by user id — no DB needed.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.routes.auth import get_current_user

try:
    from app.models.models import User  # type: ignore
except Exception:  # pragma: no cover
    User = Any  # type: ignore

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

OVERTIME_THRESHOLD_MINUTES = 8 * 60  # overtime after 8h/day

# user_id (str) -> list of shift dicts (chronological)
_SHIFTS_BY_USER: Dict[str, List[Dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _now_iso() -> str:
    return _now().isoformat() + "Z"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid ISO date: {value}")


def _user_id(user: Any) -> str:
    return str(getattr(user, "id", "unknown"))


def _user_name(user: Any) -> Optional[str]:
    return getattr(user, "full_name", None) or getattr(user, "email", None)


def _open_shift(user_id: str) -> Optional[Dict[str, Any]]:
    for shift in _SHIFTS_BY_USER.get(str(user_id), []):
        if shift.get("clock_out") is None:
            return shift
    return None


def _break_minutes(shift: Dict[str, Any], now: Optional[datetime] = None) -> float:
    now = now or _now()
    total = 0.0
    for br in shift.get("breaks", []):
        start = _parse_iso(br.get("start")) if br.get("start") else None
        end = _parse_iso(br.get("end")) if br.get("end") else None
        if start and end:
            total += max(0.0, (end - start).total_seconds() / 60.0)
        elif start and br.get("end") is None:
            total += max(0.0, (now - start).total_seconds() / 60.0)
    return round(total, 2)


def _split_overtime(worked_minutes: float) -> Dict[str, float]:
    worked = max(0.0, round(float(worked_minutes or 0), 2))
    overtime = round(max(0.0, worked - OVERTIME_THRESHOLD_MINUTES), 2)
    regular = round(worked - overtime, 2)
    return {
        "duration_minutes": worked,
        "regular_minutes": regular,
        "overtime_minutes": overtime,
        "regular_hours": round(regular / 60.0, 2),
        "overtime_hours": round(overtime / 60.0, 2),
        "hours": round(worked / 60.0, 2),
    }


def _elapsed_minutes(shift: Dict[str, Any], now: Optional[datetime] = None) -> float:
    now = now or _now()
    start = _parse_iso(shift.get("clock_in"))
    end = _parse_iso(shift.get("clock_out")) if shift.get("clock_out") else now
    if not start or not end:
        return 0.0
    gross = max(0.0, (end - start).total_seconds() / 60.0)
    return round(max(0.0, gross - _break_minutes(shift, now)), 2)


def _totals(shifts: List[Dict[str, Any]]) -> Dict[str, Any]:
    hours = round(sum(float(s.get("hours", 0) or 0) for s in shifts), 2)
    overtime = round(sum(float(s.get("overtime_hours", 0) or 0) for s in shifts), 2)
    return {"shifts": len(shifts), "hours": hours, "overtime_hours": overtime}


def _in_range(shift: Dict[str, Any], start: Optional[datetime], end: Optional[datetime]) -> bool:
    clock_in = _parse_iso(shift.get("clock_in"))
    if not clock_in:
        return False
    if start and clock_in < start:
        return False
    if end and clock_in > end:
        return False
    return True


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ClockInBody(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None


class ClockOutBody(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Clock in / out
# ---------------------------------------------------------------------------
@router.post("/clock-in")
async def clock_in(data: Optional[ClockInBody] = None, current_user=Depends(get_current_user)):
    uid = _user_id(current_user)
    if _open_shift(uid) is not None:
        raise HTTPException(status_code=400, detail="Already clocked in — close the open shift first")
    now_iso = _now_iso()
    shift = {
        "shift_id": uuid4().hex[:12],
        "user_id": uid,
        "user_name": _user_name(current_user),
        "clock_in": now_iso,
        "clock_out": None,
        "clock_in_location": {
            "latitude": data.latitude if data else None,
            "longitude": data.longitude if data else None,
        },
        "clock_out_location": None,
        "notes": data.notes if data else None,
        "clock_out_notes": None,
        "breaks": [],
        "date": now_iso[:10],
        "status": "open",
        **_split_overtime(0),
    }
    _SHIFTS_BY_USER.setdefault(uid, []).append(shift)
    return shift


@router.post("/clock-out")
async def clock_out(data: Optional[ClockOutBody] = None, current_user=Depends(get_current_user)):
    uid = _user_id(current_user)
    shift = _open_shift(uid)
    if shift is None:
        raise HTTPException(status_code=400, detail="Not clocked in — no open shift to close")
    now = _now()
    now_iso = now.isoformat() + "Z"
    # Auto-close any open break at clock-out (unpaid).
    for br in shift.get("breaks", []):
        if br.get("end") is None:
            br["end"] = now_iso
            start = _parse_iso(br.get("start"))
            br["minutes"] = round(max(0.0, (now - start).total_seconds() / 60.0), 2) if start else 0.0
    shift["clock_out"] = now_iso
    shift["clock_out_location"] = {
        "latitude": data.latitude if data else None,
        "longitude": data.longitude if data else None,
    }
    if data and data.notes:
        shift["clock_out_notes"] = data.notes
    shift["break_minutes"] = _break_minutes(shift, now)
    shift.update(_split_overtime(_elapsed_minutes(shift, now)))
    shift["status"] = "completed"
    return shift


# ---------------------------------------------------------------------------
# History & status
# ---------------------------------------------------------------------------
@router.get("/me")
async def my_shifts(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    current_user=Depends(get_current_user),
):
    end = _parse_iso(end_date) or _now()
    start = _parse_iso(start_date) or (end - timedelta(days=30))
    shifts = [s for s in _SHIFTS_BY_USER.get(_user_id(current_user), []) if _in_range(s, start, end)]
    return {"shifts": shifts, "totals": _totals(shifts)}


@router.get("/team")
async def team_shifts(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    current_user=Depends(get_current_user),
):
    """Owner/manager view: all users' shifts in range with user names."""
    end = _parse_iso(end_date) or _now()
    start = _parse_iso(start_date) or (end - timedelta(days=30))
    shifts: List[Dict[str, Any]] = []
    for user_shifts in _SHIFTS_BY_USER.values():
        shifts.extend(s for s in user_shifts if _in_range(s, start, end))
    shifts.sort(key=lambda s: s.get("clock_in") or "")
    return {"shifts": shifts, "totals": _totals(shifts)}


@router.get("/status")
async def live_status(current_user=Depends(get_current_user)):
    uid = _user_id(current_user)
    now = _now()
    shift = _open_shift(uid)
    today = now.date().isoformat()
    today_minutes = 0.0
    for s in _SHIFTS_BY_USER.get(uid, []):
        clock_in = _parse_iso(s.get("clock_in"))
        if clock_in and clock_in.date().isoformat() == today:
            if s.get("clock_out") is None:
                today_minutes += _elapsed_minutes(s, now)
            else:
                today_minutes += float(s.get("duration_minutes", 0) or 0)
    return {
        "clocked_in": shift is not None,
        "shift": shift,
        "today_hours": round(today_minutes / 60.0, 2),
        "today_minutes": round(today_minutes, 2),
    }


# ---------------------------------------------------------------------------
# Unpaid breaks inside the open shift
# ---------------------------------------------------------------------------
@router.post("/break/start")
async def break_start(current_user=Depends(get_current_user)):
    shift = _open_shift(_user_id(current_user))
    if shift is None:
        raise HTTPException(status_code=400, detail="Not clocked in — no open shift")
    for br in shift.get("breaks", []):
        if br.get("end") is None:
            raise HTTPException(status_code=400, detail="A break is already in progress")
    shift.setdefault("breaks", []).append({"start": _now_iso(), "end": None, "minutes": None})
    shift["on_break"] = True
    return shift


@router.post("/break/end")
async def break_end(current_user=Depends(get_current_user)):
    shift = _open_shift(_user_id(current_user))
    if shift is None:
        raise HTTPException(status_code=400, detail="Not clocked in — no open shift")
    open_break = next((br for br in shift.get("breaks", []) if br.get("end") is None), None)
    if open_break is None:
        raise HTTPException(status_code=400, detail="No break in progress")
    now = _now()
    open_break["end"] = now.isoformat() + "Z"
    start = _parse_iso(open_break.get("start"))
    open_break["minutes"] = round(max(0.0, (now - start).total_seconds() / 60.0), 2) if start else 0.0
    shift["on_break"] = False
    shift["break_minutes"] = _break_minutes(shift, now)
    return shift
