from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
from app.core.database import get_db
from app.routes.auth import get_current_user
from app.models.models import User

router = APIRouter(prefix="/api/uk-compliance", tags=["uk-compliance"])


# ─── In-memory stores ───
eicr_store: dict[str, dict] = {}
sfg20_store: dict[str, dict] = {}
partp_store: dict[str, dict] = {}


def generate_number(prefix: str, store: dict) -> str:
    year = datetime.utcnow().year
    seq = len([k for k in store if store[k]["created_at"].year == year]) + 1
    return f"{prefix}-{year}-{seq:05d}"


def add_created_at(record: dict) -> dict:
    record["created_at"] = datetime.utcnow()
    return record


# ─────────────────────────── EICR ───────────────────────────

class EICRCreate(BaseModel):
    customer_id: Optional[str] = None
    property_address: str
    property_type: str
    installation_age: str
    total_observations: int
    code1_count: int = 0
    code2_count: int = 0
    code3_count: int = 0
    code4_count: int = 0
    overall_result: str
    next_inspection_date: str
    engineer_name: str
    engineer_certificate_number: str
    distribution_board_details: Optional[str] = None
    notes: Optional[str] = None


@router.post("/eicr/create")
async def create_eicr(body: EICRCreate):
    if body.overall_result not in ("satisfactory", "unsatisfactory"):
        raise HTTPException(status_code=400, detail="overall_result must be 'satisfactory' or 'unsatisfactory'")

    record_id = str(uuid4())
    eicr_number = generate_number("EICR", eicr_store)

    record = add_created_at({
        "id": record_id,
        "eicr_number": eicr_number,
        **body.dict(),
    })
    eicr_store[record_id] = record
    return {"id": record_id, "eicr_number": eicr_number}


@router.get("/eicr/list")
async def list_eicr(
    result: Optional[str] = Query(None),
    property_type: Optional[str] = Query(None),
):
    records = list(eicr_store.values())
    if result:
        records = [r for r in records if r["overall_result"] == result]
    if property_type:
        records = [r for r in records if r["property_type"] == property_type]
    records.sort(key=lambda r: r["created_at"], reverse=True)
    return records


@router.get("/eicr/expiring")
async def eicr_expiring(months: int = Query(6)):
    cutoff = datetime.utcnow() + timedelta(days=months * 30)
    now = datetime.utcnow()
    expiring = [
        r for r in eicr_store.values()
        if datetime.fromisoformat(r["next_inspection_date"]) <= cutoff
        and datetime.fromisoformat(r["next_inspection_date"]) >= now
    ]
    expiring.sort(key=lambda r: r["next_inspection_date"])
    return expiring


@router.get("/eicr/{eicr_id}")
async def get_eicr(eicr_id: str):
    record = eicr_store.get(eicr_id)
    if not record:
        raise HTTPException(status_code=404, detail="EICR not found")
    return record


# ─────────────────────────── SFG20 ───────────────────────────

class MaintenanceTask(BaseModel):
    task_name: str
    frequency: str
    sfg20_code: Optional[str] = None
    description: Optional[str] = None


class SFG20ScheduleCreate(BaseModel):
    customer_id: Optional[str] = None
    property_address: str
    asset_type: str
    asset_description: Optional[str] = None
    maintenance_tasks: List[MaintenanceTask]
    contract_start_date: str
    contract_end_date: str


class TaskComplete(BaseModel):
    task_index: int
    completion_date: str
    notes: Optional[str] = None
    engineer_name: Optional[str] = None


FREQUENCY_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 91,
    "annually": 365,
}


def calculate_next_date(start: str, frequency: str) -> str:
    days = FREQUENCY_DAYS.get(frequency, 30)
    return (datetime.fromisoformat(start) + timedelta(days=days)).date().isoformat()


@router.post("/sfg20/schedule")
async def create_sfg20(body: SFG20ScheduleCreate):
    record_id = str(uuid4())
    schedule_number = generate_number("SFG", sfg20_store)

    tasks = []
    for i, t in enumerate(body.maintenance_tasks):
        if t.frequency not in FREQUENCY_DAYS:
            raise HTTPException(status_code=400, detail=f"Invalid frequency '{t.frequency}' for task '{t.task_name}'")
        tasks.append({
            **t.dict(),
            "completed": False,
            "last_completed": None,
            "next_due": body.contract_start_date,
            "completion_history": [],
        })

    record = add_created_at({
        "id": record_id,
        "schedule_number": schedule_number,
        **body.dict(exclude={"maintenance_tasks"}),
        "tasks": tasks,
        "status": "active",
    })
    sfg20_store[record_id] = record
    return {"id": record_id, "schedule_number": schedule_number}


@router.get("/sfg20/list")
async def list_sfg20(status: Optional[str] = Query(None)):
    records = list(sfg20_store.values())
    if status:
        records = [r for r in records if r["status"] == status]
    records.sort(key=lambda r: r["created_at"], reverse=True)
    return records


@router.get("/sfg20/due")
async def sfg20_due(period: str = Query("week")):
    now = datetime.utcnow().date()
    days = 7 if period == "week" else 30
    cutoff = now + timedelta(days=days)

    due_tasks = []
    for schedule in sfg20_store.values():
        if schedule["status"] != "active":
            continue
        for i, task in enumerate(schedule["tasks"]):
            next_due = datetime.fromisoformat(task["next_due"]).date() if task["next_due"] else None
            if next_due and next_due <= cutoff:
                due_tasks.append({
                    "schedule_id": schedule["id"],
                    "schedule_number": schedule["schedule_number"],
                    "property_address": schedule["property_address"],
                    "task_index": i,
                    "task_name": task["task_name"],
                    "frequency": task["frequency"],
                    "sfg20_code": task.get("sfg20_code"),
                    "next_due": task["next_due"],
                })
    due_tasks.sort(key=lambda t: t["next_due"])
    return due_tasks


@router.get("/sfg20/{schedule_id}")
async def get_sfg20(schedule_id: str):
    record = sfg20_store.get(schedule_id)
    if not record:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return record


@router.post("/sfg20/{schedule_id}/complete-task")
async def complete_sfg20_task(schedule_id: str, body: TaskComplete):
    record = sfg20_store.get(schedule_id)
    if not record:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if body.task_index < 0 or body.task_index >= len(record["tasks"]):
        raise HTTPException(status_code=400, detail="Invalid task index")

    task = record["tasks"][body.task_index]
    task["completed"] = True
    task["last_completed"] = body.completion_date
    task["completion_history"].append({
        "date": body.completion_date,
        "notes": body.notes,
        "engineer_name": body.engineer_name,
    })

    next_due = calculate_next_date(body.completion_date, task["frequency"])
    contract_end = datetime.fromisoformat(record["contract_end_date"]).date()
    if datetime.fromisoformat(next_due).date() > contract_end:
        task["next_due"] = None
        task["completed"] = True
    else:
        task["next_due"] = next_due
        task["completed"] = False

    return {"success": True, "next_due": task["next_due"]}


# ─────────────────────────── Part P ───────────────────────────

class PartPNotify(BaseModel):
    customer_id: Optional[str] = None
    property_address: str
    work_description: str
    work_type: str
    notification_type: str
    building_control_body: Optional[str] = None
    submission_date: str


WORK_TYPES = ("new_install", "alteration", "addition")
NOTIFICATION_TYPES = ("full", "partial", "building_notice")


@router.post("/part-p/notify")
async def notify_building_control(body: PartPNotify):
    if body.work_type not in WORK_TYPES:
        raise HTTPException(status_code=400, detail=f"work_type must be one of {WORK_TYPES}")
    if body.notification_type not in NOTIFICATION_TYPES:
        raise HTTPException(status_code=400, detail=f"notification_type must be one of {NOTIFICATION_TYPES}")

    record_id = str(uuid4())
    notification_number = generate_number("PP", partp_store)

    record = add_created_at({
        "id": record_id,
        "notification_number": notification_number,
        **body.dict(),
        "status": "submitted",
        "approval_date": None,
        "completion_certificate_issued": False,
    })
    partp_store[record_id] = record
    return {"id": record_id, "notification_number": notification_number, "status": "submitted"}


@router.get("/part-p/list")
async def list_partp(status: Optional[str] = Query(None)):
    records = list(partp_store.values())
    if status:
        records = [r for r in records if r["status"] == status]
    records.sort(key=lambda r: r["created_at"], reverse=True)
    return records


@router.get("/part-p/{notification_id}")
async def get_partp(notification_id: str):
    record = partp_store.get(notification_id)
    if not record:
        raise HTTPException(status_code=404, detail="Notification not found")
    return record
