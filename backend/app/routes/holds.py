"""Appointment holds — double-book guard (Allo).

Prefix: /api/holds

Overlap rule: (starts < ends_at) AND (ends > starts_at), scoped to the
same business, counting held (unexpired) + confirmed holds only.

Create is check-then-insert inside a single transaction with a re-check
after flush; a conflict rolls back. No DB exclusion constraint exists
yet (see FOLLOW-UP), so serializable-level races are still possible —
honestly reported below.

All endpoints degrade gracefully (never 500). Auth 401s and explicit
404/409/422 HTTPExceptions still propagate.

FOLLOW-UP (integrator): add a Postgres EXCLUDE constraint on
(tsrange(starts_at, ends_at)) for true serializable safety, and a
background sweeper for expired `held` rows.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import AppointmentHold, Business, CampaignMember, User
from app.routes.agents import _make_lead_reference
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/holds", tags=["holds"])


class HoldCheck(BaseModel):
    starts_at: datetime
    ends_at: datetime


class HoldCreate(BaseModel):
    member_id: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    ttl_min: int = Field(default=15, ge=1, le=1440)


def _active_overlap(business_id, starts: datetime, ends: datetime):
    """Overlap predicate: same business, held (unexpired) or confirmed."""
    now = datetime.utcnow()
    return and_(
        AppointmentHold.business_id == business_id,
        AppointmentHold.starts_at < ends,
        AppointmentHold.ends_at > starts,
        or_(
            AppointmentHold.status == "confirmed",
            and_(
                AppointmentHold.status == "held",
                or_(
                    AppointmentHold.expires_at.is_(None),
                    AppointmentHold.expires_at > now,
                ),
            ),
        ),
    )


async def _get_business(db: AsyncSession, user: User) -> Optional[Business]:
    """Owner -> business lookup (mirrors sms.py). Never raises."""
    try:
        result = await db.execute(
            select(Business).where(Business.owner_id == user.id)
        )
        return result.scalar_one_or_none()
    except Exception:
        return None


def _validate_window(starts: datetime, ends: datetime) -> None:
    if starts >= ends:
        raise HTTPException(
            status_code=422, detail="ends_at must be after starts_at"
        )


def _hold_out(hold: AppointmentHold) -> dict:
    return {
        "hold_ref": hold.hold_ref,
        "status": hold.status,
        "starts_at": hold.starts_at.isoformat() if hold.starts_at else None,
        "ends_at": hold.ends_at.isoformat() if hold.ends_at else None,
        "expires_at": hold.expires_at.isoformat() if hold.expires_at else None,
        "member_id": str(hold.member_id) if hold.member_id else None,
    }


@router.post("/check")
async def check_availability(
    data: HoldCheck,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return {available: bool} for the window. Never 500."""
    try:
        _validate_window(data.starts_at, data.ends_at)
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        result = await db.execute(
            select(AppointmentHold.id)
            .where(_active_overlap(business.id, data.starts_at, data.ends_at))
            .limit(1)
        )
        return {"ok": True, "available": result.scalar_one_or_none() is None}
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "available": False}


@router.post("/")
async def create_hold(
    data: HoldCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Atomic check-then-insert; re-checks inside the transaction and
    rolls back on conflict. Returns hold_ref. Never 500."""
    try:
        _validate_window(data.starts_at, data.ends_at)
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")

        member_pk = None
        if data.member_id:
            try:
                result = await db.execute(
                    select(CampaignMember).where(
                        CampaignMember.id == data.member_id,
                        CampaignMember.business_id == business.id,
                    )
                )
                member = result.scalar_one_or_none()
                if member is None:
                    raise HTTPException(
                        status_code=422, detail="Unknown member_id"
                    )
                member_pk = member.id
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(
                    status_code=422, detail="Invalid member_id"
                )

        # Check inside the transaction, then insert, then re-check.
        conflict = await db.execute(
            select(AppointmentHold.id)
            .where(_active_overlap(business.id, data.starts_at, data.ends_at))
            .limit(1)
        )
        if conflict.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Slot unavailable")

        hold_ref = _make_lead_reference()
        for _ in range(3):  # hold_ref unique — regenerate on collision
            try:
                existing = await db.execute(
                    select(AppointmentHold.id).where(
                        AppointmentHold.hold_ref == hold_ref
                    )
                )
                if existing.scalar_one_or_none() is None:
                    break
                hold_ref = _make_lead_reference()
            except Exception:
                break

        hold = AppointmentHold(
            business_id=business.id,
            member_id=member_pk,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            hold_ref=hold_ref,
            status="held",
            expires_at=datetime.utcnow() + timedelta(minutes=data.ttl_min),
        )
        db.add(hold)
        await db.flush()

        recheck = await db.execute(
            select(AppointmentHold.id).where(
                _active_overlap(business.id, data.starts_at, data.ends_at),
                AppointmentHold.id != hold.id,
            ).limit(1)
        )
        if recheck.scalar_one_or_none() is not None:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Slot unavailable")

        await db.commit()
        await db.refresh(hold)
        out = {"ok": True, "available": True}
        out.update(_hold_out(hold))
        return out
    except HTTPException:
        try:
            await db.rollback()
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)[:300]}


@router.post("/{hold_ref}/confirm")
async def confirm_hold(
    hold_ref: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """held -> confirmed. Never 500."""
    try:
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        result = await db.execute(
            select(AppointmentHold).where(
                AppointmentHold.hold_ref == (hold_ref or "").strip(),
                AppointmentHold.business_id == business.id,
            )
        )
        hold = result.scalar_one_or_none()
        if hold is None:
            raise HTTPException(status_code=404, detail="Hold not found")
        if hold.status == "released":
            raise HTTPException(
                status_code=409, detail="Hold already released"
            )
        hold.status = "confirmed"
        await db.commit()
        await db.refresh(hold)
        out = {"ok": True}
        out.update(_hold_out(hold))
        return out
    except HTTPException:
        try:
            await db.rollback()
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)[:300]}


@router.post("/{hold_ref}/release")
async def release_hold(
    hold_ref: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Any status -> released (idempotent). Never 500."""
    try:
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        result = await db.execute(
            select(AppointmentHold).where(
                AppointmentHold.hold_ref == (hold_ref or "").strip(),
                AppointmentHold.business_id == business.id,
            )
        )
        hold = result.scalar_one_or_none()
        if hold is None:
            raise HTTPException(status_code=404, detail="Hold not found")
        hold.status = "released"
        await db.commit()
        await db.refresh(hold)
        out = {"ok": True}
        out.update(_hold_out(hold))
        return out
    except HTTPException:
        try:
            await db.rollback()
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)[:300]}
