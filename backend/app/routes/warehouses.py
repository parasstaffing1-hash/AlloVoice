"""Warehouse / depot stock transfers for VoiceField (UK field service SaaS).

Times are ISO-8601 UTC (``datetime.utcnow().isoformat() + "Z"``); display in
Europe/London (en-GB) on the client.

Storage is in-memory (module level) dicts — no DB dependency. Stock levels
are tracked in the module ``_STOCK`` dict. ``InventoryItem`` is imported
defensively (read-only reference): if the model is unavailable or lacks
warehouse/location fields we simply track transfer records in memory.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.routes.auth import get_current_user

try:  # Optional reference only; stock is tracked in-memory regardless.
    from app.models.models import InventoryItem  # type: ignore

    _INV_COLUMNS = set(getattr(getattr(InventoryItem, "__table__", None), "columns", {}).keys()) \
        if hasattr(getattr(InventoryItem, "__table__", None), "columns") else set()
    _HAS_LOCATION_FIELDS = bool(
        _INV_COLUMNS & {"location_id", "warehouse_id", "depot_id", "location", "warehouse"}
    )
except Exception:  # pragma: no cover - model/env may vary
    InventoryItem = None  # type: ignore
    _HAS_LOCATION_FIELDS = False

try:
    from app.models.models import User  # type: ignore
except Exception:  # pragma: no cover
    User = Any  # type: ignore

router = APIRouter(prefix="/api/warehouses", tags=["warehouses"])

# ---------------------------------------------------------------------------
# In-memory storage (module level)
# ---------------------------------------------------------------------------
_WAREHOUSES: Dict[str, Dict[str, Any]] = {}
_TRANSFERS: Dict[str, Dict[str, Any]] = {}
# warehouse_id -> sku -> {sku, name, quantity}
_STOCK: Dict[str, Dict[str, Dict[str, Any]]] = {}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _stock_list(warehouse_id: str) -> List[Dict[str, Any]]:
    return [
        {"sku": sku, "name": entry.get("name"), "quantity": entry.get("quantity", 0)}
        for sku, entry in sorted(_STOCK.get(warehouse_id, {}).items())
    ]


def _warehouse_summary(wh: Dict[str, Any]) -> Dict[str, Any]:
    wid = wh["id"]
    stock = _STOCK.get(wid, {})
    linked_transfers = sum(
        1 for t in _TRANSFERS.values()
        if t.get("from_warehouse_id") == wid or t.get("to_warehouse_id") == wid
    )
    return {
        **wh,
        "sku_count": len(stock),
        "stock_quantity": sum(float(e.get("quantity", 0) or 0) for e in stock.values()),
        "item_count": len(stock),
        "transfers_count": linked_transfers,
    }


def _normalise_items(raw_items: Any) -> List[Dict[str, Any]]:
    """Accept [{sku|item_id, name, quantity}] -> [{sku, name, quantity}]."""
    if not isinstance(raw_items, list) or not raw_items:
        raise HTTPException(status_code=400, detail="items must be a non-empty list")
    normalised: List[Dict[str, Any]] = []
    for entry in raw_items:
        if isinstance(entry, BaseModel):
            entry = entry.model_dump()
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400, detail="Each item must be an object")
        sku = entry.get("sku") or entry.get("item_id")
        name = entry.get("name")
        quantity = entry.get("quantity")
        if not sku:
            raise HTTPException(status_code=400, detail="Each item needs a sku (or item_id)")
        try:
            qty = float(quantity)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid quantity for sku {sku}")
        if qty <= 0:
            raise HTTPException(status_code=400, detail=f"Quantity must be positive for sku {sku}")
        normalised.append({"sku": str(sku), "name": name or str(sku), "quantity": qty})
    return normalised


def _ensure_warehouse(warehouse_id: str) -> Dict[str, Any]:
    wh = _WAREHOUSES.get(str(warehouse_id))
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return wh


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class WarehouseCreate(BaseModel):
    name: str = Field(..., min_length=1)
    address: Optional[str] = None
    postcode: Optional[str] = None
    is_default: bool = False


class TransferItemIn(BaseModel):
    sku: Optional[str] = None
    item_id: Optional[str] = None
    name: Optional[str] = None
    quantity: float


class TransferCreate(BaseModel):
    from_warehouse_id: str
    to_warehouse_id: str
    items: List[TransferItemIn]
    notes: Optional[str] = None
    requested_by: Optional[str] = None


class ReceiveBody(BaseModel):
    received_items: Optional[List[TransferItemIn]] = None
    notes: Optional[str] = None


class AdjustBody(BaseModel):
    sku: str = Field(..., min_length=1)
    name: Optional[str] = None
    quantity_change: float
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Depots
# ---------------------------------------------------------------------------
@router.post("", include_in_schema=False)
@router.post("/")
async def create_warehouse(data: WarehouseCreate, current_user=Depends(get_current_user)):
    wid = uuid4().hex[:12]
    is_default = bool(data.is_default)
    if is_default:
        for wh in _WAREHOUSES.values():
            wh["is_default"] = False
    elif not _WAREHOUSES:
        is_default = True  # first depot becomes default
    warehouse = {
        "id": wid,
        "name": data.name,
        "address": data.address,
        "postcode": data.postcode,
        "is_default": is_default,
        "created_at": _now_iso(),
    }
    _WAREHOUSES[wid] = warehouse
    _STOCK.setdefault(wid, {})
    return warehouse


@router.get("", include_in_schema=False)
@router.get("/")
async def list_warehouses(current_user=Depends(get_current_user)):
    return {"warehouses": [_warehouse_summary(wh) for wh in _WAREHOUSES.values()]}


# ---------------------------------------------------------------------------
# Transfers (literal routes first so they are never shadowed)
# ---------------------------------------------------------------------------
@router.post("/transfers")
async def create_transfer(data: TransferCreate, current_user=Depends(get_current_user)):
    from_id = str(data.from_warehouse_id)
    to_id = str(data.to_warehouse_id)
    if from_id == to_id:
        raise HTTPException(
            status_code=400, detail="from_warehouse_id and to_warehouse_id must differ"
        )
    _ensure_warehouse(from_id)
    _ensure_warehouse(to_id)
    items = _normalise_items([i.model_dump() for i in data.items])
    transfer_id = uuid4().hex[:12]
    transfer = {
        "id": transfer_id,
        "from_warehouse_id": from_id,
        "to_warehouse_id": to_id,
        "items": items,
        "notes": data.notes,
        "requested_by": data.requested_by
        or getattr(current_user, "full_name", None)
        or getattr(current_user, "email", None),
        "status": "in_transit",
        "created_at": _now_iso(),
        "received_at": None,
        "received_items": None,
    }
    _TRANSFERS[transfer_id] = transfer
    return transfer


@router.get("/transfers/list")
async def list_transfers(
    status: Optional[str] = Query(default=None),
    warehouse_id: Optional[str] = Query(default=None),
    current_user=Depends(get_current_user),
):
    transfers = list(_TRANSFERS.values())
    if status:
        transfers = [t for t in transfers if t.get("status") == status]
    if warehouse_id:
        wid = str(warehouse_id)
        transfers = [
            t
            for t in transfers
            if t.get("from_warehouse_id") == wid or t.get("to_warehouse_id") == wid
        ]
    return {"transfers": transfers}


@router.post("/transfers/{transfer_id}/receive")
async def receive_transfer(
    transfer_id: str, data: Optional[ReceiveBody] = None, current_user=Depends(get_current_user)
):
    transfer = _TRANSFERS.get(str(transfer_id))
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if transfer.get("status") in ("completed", "partially_completed", "partial"):
        raise HTTPException(status_code=400, detail="Transfer has already been received")

    from_id = transfer["from_warehouse_id"]
    to_id = transfer["to_warehouse_id"]
    _ensure_warehouse(from_id)
    _ensure_warehouse(to_id)

    requested = {i["sku"]: i for i in transfer.get("items", [])}
    if data and data.received_items:
        received = _normalise_items([i.model_dump() for i in data.received_items])
    else:
        received = [
            {"sku": sku, "name": info.get("name"), "quantity": info.get("quantity", 0)}
            for sku, info in requested.items()
        ]

    received_map = {i["sku"]: i for i in received}
    unknown = set(received_map) - set(requested)
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"Received items not on transfer: {sorted(unknown)}"
        )

    complete = all(
        received_map.get(sku, {}).get("quantity", 0) >= info.get("quantity", 0)
        for sku, info in requested.items()
    )
    status_value = "completed" if complete else "partial"

    src = _STOCK.setdefault(from_id, {})
    dst = _STOCK.setdefault(to_id, {})
    for sku, item in received_map.items():
        qty = float(item.get("quantity", 0) or 0)
        name = item.get("name") or requested[sku].get("name") or sku
        src_entry = src.setdefault(sku, {"sku": sku, "name": name, "quantity": 0})
        src_entry["quantity"] = float(src_entry.get("quantity", 0) or 0) - qty
        dst_entry = dst.setdefault(sku, {"sku": sku, "name": name, "quantity": 0})
        dst_entry["quantity"] = float(dst_entry.get("quantity", 0) or 0) + qty

    transfer["received_items"] = received
    transfer["status"] = status_value
    transfer["received_at"] = _now_iso()
    if data and data.notes:
        transfer["receive_notes"] = data.notes
    transfer["received_by"] = getattr(current_user, "full_name", None) or getattr(
        current_user, "email", None
    )
    return transfer


# ---------------------------------------------------------------------------
# Depot detail + stock adjustment
# ---------------------------------------------------------------------------
@router.get("/{warehouse_id}")
async def get_warehouse(warehouse_id: str, current_user=Depends(get_current_user)):
    warehouse = _ensure_warehouse(warehouse_id)
    return {**warehouse, "stock": _stock_list(warehouse["id"])}


@router.post("/{warehouse_id}/adjust")
async def adjust_stock(
    warehouse_id: str, data: AdjustBody, current_user=Depends(get_current_user)
):
    warehouse = _ensure_warehouse(warehouse_id)
    wid = warehouse["id"]
    sku = str(data.sku)
    try:
        delta = float(data.quantity_change)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="quantity_change must be a number")
    stock = _STOCK.setdefault(wid, {})
    entry = stock.setdefault(sku, {"sku": sku, "name": data.name or sku, "quantity": 0})
    if data.name:
        entry["name"] = data.name
    entry["quantity"] = float(entry.get("quantity", 0) or 0) + delta
    return {
        "sku": sku,
        "name": entry.get("name"),
        "new_quantity": entry.get("quantity", 0),
        "quantity_change": delta,
        "reason": data.reason,
        "warehouse_id": wid,
    }
