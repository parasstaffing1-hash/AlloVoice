"""Dues-collection calling engine (Allo).

Prefix: /api/collections

Queued-first voice collection: overdue invoices are listed, selected
invoices are queued as CollectionAttempt rows, and each attempt triggers
a single Twilio outbound call to /api/telephony/voice.

Compliance (baked in, not optional):
- Calling window 08:00-20:00 caller-local Europe/London (business
  timezone when set). Queue + call outside the window return
  {ok: False, reason} — never a call, never a 500.
- Max 1 call attempt per phone per day (queue skips phones already
  queued/called today; call refuses when another attempt for the same
  phone was already queued/called today).
- SMS inbound STOP handling is NOT owned here — this router sends voice
  calls only and emits no SMS, so there is no inbound text path to
  handle. STOP/opt-out recorded via outcome=opted_out only.

All endpoints degrade gracefully (never 500). Auth 401s and explicit
404/422 HTTPExceptions still propagate.
"""

from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import (
    Business,
    CollectionAttempt,
    Customer,
    GdprErasureRequest,
    Invoice,
    PaymentStatus,
    User,
)
from app.routes.agents import _make_lead_reference
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/collections", tags=["collections"])

CALL_WINDOW_START_HOUR = 8
CALL_WINDOW_END_HOUR = 20  # exclusive
DEFAULT_TZ = "Europe/London"
ACTIVE_PHONE_STATUSES = ("queued", "called", "answered")
OUTCOME_STATUSES = ("promised", "paid", "disputed", "opted_out", "no_answer")
OVERDUE_STATUSES = (
    PaymentStatus.PENDING,
    PaymentStatus.OVERDUE,
    PaymentStatus.PARTIALLY_PAID,
)


class QueueBody(BaseModel):
    invoice_ids: List[str] = Field(default_factory=list)


class OutcomeBody(BaseModel):
    outcome: str = Field(min_length=1, max_length=20)
    promise_date: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=2000)


async def _get_business(db: AsyncSession, user: User) -> Optional[Business]:
    """Owner -> business lookup (mirrors holds.py). Never raises."""
    try:
        result = await db.execute(
            select(Business).where(Business.owner_id == user.id)
        )
        return result.scalar_one_or_none()
    except Exception:
        return None


def _business_tz(business: Optional[Business]) -> str:
    try:
        tz = (getattr(business, "timezone", "") or "").strip()
        if tz:
            ZoneInfo(tz)
            return tz
    except Exception:
        pass
    return DEFAULT_TZ


def _in_calling_window(business: Optional[Business] = None) -> bool:
    """True when caller-local time is 08:00-20:00. Never raises."""
    try:
        now_local = datetime.now(timezone.utc).astimezone(
            ZoneInfo(_business_tz(business))
        )
        return CALL_WINDOW_START_HOUR <= now_local.hour < CALL_WINDOW_END_HOUR
    except Exception:
        try:
            return (
                CALL_WINDOW_START_HOUR
                <= datetime.now(timezone.utc).hour
                < CALL_WINDOW_END_HOUR
            )
        except Exception:
            return True


def _window_reason(business: Optional[Business] = None) -> str:
    return (
        "Outside calling window (08:00-20:00 %s). "
        "Attempt kept queued — retry inside the window." % _business_tz(business)
    )


def _today_start_utc() -> datetime:
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _outstanding_pence(invoice: Invoice) -> int:
    try:
        total = float(invoice.total or 0)
    except Exception:
        total = 0.0
    try:
        paid = float(invoice.amount_paid or 0)
    except Exception:
        paid = 0.0
    return max(0, int(round((total - paid) * 100)))


def _attempt_out(attempt: CollectionAttempt) -> dict:
    return {
        "attempt_id": str(attempt.id),
        "invoice_id": str(attempt.invoice_id) if attempt.invoice_id else None,
        "customer_name": attempt.customer_name,
        "phone": attempt.phone,
        "amount_pence": attempt.amount_pence,
        "channel": attempt.channel,
        "status": attempt.status,
        "outcome_note": attempt.outcome_note,
        "promise_date": attempt.promise_date.isoformat()
        if attempt.promise_date
        else None,
        "call_sid": attempt.call_sid,
        "created_at": attempt.created_at.isoformat()
        if attempt.created_at
        else None,
    }


async def _phone_attempted_today(
    db: AsyncSession,
    business_id,
    phone: str,
    exclude_id=None,
) -> bool:
    """Another non-failed attempt for this phone created today? Never raises."""
    try:
        stmt = select(CollectionAttempt.id).where(
            CollectionAttempt.business_id == business_id,
            CollectionAttempt.phone == phone,
            CollectionAttempt.created_at >= _today_start_utc(),
            CollectionAttempt.status.in_(list(ACTIVE_PHONE_STATUSES)),
        )
        if exclude_id is not None:
            stmt = stmt.where(CollectionAttempt.id != exclude_id)
        result = await db.execute(stmt.limit(1))
        return result.scalar_one_or_none() is not None
    except Exception:
        return False


async def _invoice_queued_today(
    db: AsyncSession, business_id, invoice_id: str
) -> bool:
    """Same invoice already queued/called today? Never raises."""
    try:
        result = await db.execute(
            select(CollectionAttempt.id)
            .where(
                CollectionAttempt.business_id == business_id,
                CollectionAttempt.invoice_id == invoice_id,
                CollectionAttempt.created_at >= _today_start_utc(),
                CollectionAttempt.status.in_(["queued", "called"]),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
    except Exception:
        return False


async def _get_attempt(
    db: AsyncSession, business_id, attempt_id: str
) -> Optional[CollectionAttempt]:
    try:
        result = await db.execute(
            select(CollectionAttempt).where(
                CollectionAttempt.id == (attempt_id or "").strip(),
                CollectionAttempt.business_id == business_id,
            )
        )
        return result.scalar_one_or_none()
    except Exception:
        return None


@router.get("/overdue")
async def list_overdue(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List overdue invoices for the owner's business. Never 500."""
    try:
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            result = await db.execute(
                select(Invoice, Customer)
                .join(Customer, Customer.id == Invoice.customer_id)
                .where(
                    Invoice.business_id == business.id,
                    Invoice.payment_status.in_(list(OVERDUE_STATUSES)),
                    Invoice.due_date.is_not(None),
                    Invoice.due_date < now,
                )
                .order_by(Invoice.due_date.asc())
            )
            rows = result.all()
        except Exception as e:
            return {"ok": False, "error": str(e)[:300], "overdue": []}
        overdue = []
        for invoice, customer in rows:
            try:
                due = invoice.due_date
                days = (now - due).days if due else 0
                try:
                    total = float(invoice.total or 0)
                except Exception:
                    total = 0.0
                try:
                    paid = float(invoice.amount_paid or 0)
                except Exception:
                    paid = 0.0
                overdue.append(
                    {
                        "invoice_id": str(invoice.id),
                        "customer_name": getattr(customer, "full_name", None),
                        "phone": getattr(customer, "phone", None),
                        "amount": max(0.0, total - paid),
                        "days_overdue": max(0, days),
                    }
                )
            except Exception:
                continue
        return {"ok": True, "overdue": overdue}
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "overdue": []}


@router.post("/queue")
async def queue_attempts(
    data: QueueBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue collection attempts for invoice_ids. Never 500."""
    try:
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        if not _in_calling_window(business):
            return {"ok": False, "reason": _window_reason(business)}
        batch_ref = _make_lead_reference()
        queued = 0
        skipped = 0
        skipped_ids: list = []
        seen_phones: set = set()
        for raw_id in data.invoice_ids or []:
            inv_id = (raw_id or "").strip()
            if not inv_id:
                skipped += 1
                continue
            try:
                result = await db.execute(
                    select(Invoice, Customer)
                    .join(Customer, Customer.id == Invoice.customer_id)
                    .where(
                        Invoice.id == inv_id,
                        Invoice.business_id == business.id,
                    )
                )
                row = result.one_or_none()
                if row is None:
                    skipped += 1
                    skipped_ids.append(inv_id)
                    continue
                invoice, customer = row
                if invoice.payment_status in (
                    PaymentStatus.PAID,
                    PaymentStatus.REFUNDED,
                ):
                    skipped += 1
                    skipped_ids.append(inv_id)
                    continue
                phone = (getattr(customer, "phone", "") or "").strip()
                if not phone:
                    skipped += 1
                    skipped_ids.append(inv_id)
                    continue
                if await _invoice_queued_today(db, business.id, inv_id):
                    skipped += 1
                    skipped_ids.append(inv_id)
                    continue
                if (
                    phone in seen_phones
                    or await _phone_attempted_today(db, business.id, phone)
                ):
                    # Max 1 call attempt per phone per day.
                    skipped += 1
                    skipped_ids.append(inv_id)
                    continue
                attempt = CollectionAttempt(
                    business_id=business.id,
                    invoice_id=invoice.id,
                    customer_name=getattr(customer, "full_name", None),
                    phone=phone,
                    amount_pence=_outstanding_pence(invoice),
                    channel="voice",
                    status="queued",
                )
                db.add(attempt)
                await db.flush()
                seen_phones.add(phone)
                queued += 1
            except Exception:
                skipped += 1
                try:
                    skipped_ids.append(inv_id)
                except Exception:
                    pass
                continue
        try:
            await db.commit()
        except Exception as e:
            try:
                await db.rollback()
            except Exception:
                pass
            return {"ok": False, "error": str(e)[:300]}
        return {
            "ok": True,
            "queued": queued,
            "skipped": skipped,
            "skipped_ids": skipped_ids,
            "batch_ref": batch_ref,
        }
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


@router.post("/{attempt_id}/call")
async def trigger_call(
    attempt_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger the Twilio outbound call for an attempt. Never 500."""
    try:
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        attempt = await _get_attempt(db, business.id, attempt_id)
        if attempt is None:
            raise HTTPException(status_code=404, detail="Attempt not found")
        if not _in_calling_window(business):
            return {"ok": False, "reason": _window_reason(business)}
        if await _phone_attempted_today(
            db, business.id, attempt.phone, exclude_id=attempt.id
        ):
            return {
                "ok": False,
                "reason": (
                    "Phone already attempted today "
                    "(max 1 call per phone per day)."
                ),
            }
        # Read Twilio settings at call time (not import time).
        s = get_settings()
        sid = (s.TWILIO_ACCOUNT_SID or "").strip()
        token = (s.TWILIO_AUTH_TOKEN or "").strip()
        from_number = (s.TWILIO_PHONE_NUMBER or "").strip()
        public_base = (s.PUBLIC_API_URL or "").strip().rstrip("/")
        if not (sid and token and from_number):
            return {
                "ok": True,
                "queued": True,
                "attempt_id": str(attempt.id),
                "status": attempt.status,
                "message": (
                    "Twilio not configured "
                    "(TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / "
                    "TWILIO_PHONE_NUMBER missing); attempt kept queued."
                ),
            }
        voice_url = (public_base + "/api/telephony/voice") if public_base else ""
        if not voice_url:
            return {
                "ok": True,
                "queued": True,
                "attempt_id": str(attempt.id),
                "status": attempt.status,
                "message": (
                    "Twilio not configured (PUBLIC_API_URL missing); "
                    "attempt kept queued."
                ),
            }
        try:
            twilio_url = (
                "https://api.twilio.com/2010-04-01/Accounts/%s/Calls.json" % sid
            )
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    twilio_url,
                    data={
                        "From": from_number,
                        "To": attempt.phone,
                        "Url": voice_url,
                    },
                    auth=(sid, token),
                )
        except Exception as e:
            return {
                "ok": False,
                "attempt_id": str(attempt.id),
                "error": ("Twilio request failed: %s" % str(e))[:300],
            }
        if resp.status_code >= 400:
            try:
                body = resp.text[:500]
            except Exception:
                body = "Twilio error %s" % resp.status_code
            try:
                attempt.status = "failed"
                attempt.outcome_note = body
                await db.commit()
                await db.refresh(attempt)
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass
            return {
                "ok": False,
                "attempt_id": str(attempt.id),
                "error": body[:300],
            }
        try:
            payload = resp.json()
        except Exception:
            payload = {}
        call_sid = payload.get("sid") if isinstance(payload, dict) else None
        try:
            attempt.call_sid = call_sid
            attempt.status = "called"
            await db.commit()
            await db.refresh(attempt)
        except Exception as e:
            try:
                await db.rollback()
            except Exception:
                pass
            return {"ok": False, "error": str(e)[:300]}
        out = {"ok": True, "call_sid": call_sid}
        out.update(_attempt_out(attempt))
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


@router.post("/{attempt_id}/outcome")
async def record_outcome(
    attempt_id: str,
    data: OutcomeBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record the outcome of an attempt. Never 500."""
    try:
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        outcome = (data.outcome or "").strip().lower()
        if outcome not in OUTCOME_STATUSES:
            raise HTTPException(
                status_code=422,
                detail="outcome must be one of: %s" % ", ".join(OUTCOME_STATUSES),
            )
        attempt = await _get_attempt(db, business.id, attempt_id)
        if attempt is None:
            raise HTTPException(status_code=404, detail="Attempt not found")
        try:
            attempt.status = outcome
            if data.promise_date is not None:
                attempt.promise_date = data.promise_date
            if data.note:
                attempt.outcome_note = data.note[:2000]
            await db.commit()
            await db.refresh(attempt)
        except Exception as e:
            try:
                await db.rollback()
            except Exception:
                pass
            return {"ok": False, "error": str(e)[:300]}
        if outcome == "opted_out":
            # GDPR best-effort: suppress future marketing + log erasure
            # request. Must never fail the outcome write above.
            try:
                cust_result = await db.execute(
                    select(Customer).where(
                        Customer.business_id == business.id,
                        Customer.phone == attempt.phone,
                    )
                )
                customer = cust_result.scalar_one_or_none()
                if customer is not None:
                    customer.marketing_consent = False
                    db.add(
                        GdprErasureRequest(
                            business_id=business.id,
                            customer_id=customer.id,
                            status="pending",
                            notes=((data.note or "collections opt-out")[:500]),
                        )
                    )
                    await db.commit()
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass
        out = {"ok": True}
        out.update(_attempt_out(attempt))
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


@router.get("/stats")
async def collection_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Counts by status for the business. Never 500."""
    try:
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        try:
            result = await db.execute(
                select(CollectionAttempt.status, func.count(CollectionAttempt.id))
                .where(CollectionAttempt.business_id == business.id)
                .group_by(CollectionAttempt.status)
            )
            counts = {status: int(n) for status, n in result.all()}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300], "counts": {}}
        return {"ok": True, "counts": counts}
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "counts": {}}
