"""Stale-lead resurrection campaigns (Allo).

Prefix: /api/campaigns

QUEUED-ONLY outreach: Twilio creds are blanked in this build, so no real
SMS is sent. run-step marks members `contacted` (queued) and writes
`sms_logs` rows with status="queued" — honestly reported in the response.

All endpoints degrade gracefully (never 500). Auth 401s and explicit
404/422 HTTPExceptions still propagate.
"""

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import (
    Business,
    CampaignMember,
    Customer,
    GdprConsent,
    LeadCampaign,
    SmsLog,
    User,
)
from app.routes.agents import _make_lead_reference
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

ALLOWED_KINDS = ("ppc_resurrection", "stale_db")
RUN_STEP_LIMIT = 25
IMPORT_CAP = 1000


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(min_length=1, max_length=32)


class MemberIn(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class ImportBody(BaseModel):
    members: List[MemberIn] = Field(default_factory=list)


async def _get_business(db: AsyncSession, user: User) -> Optional[Business]:
    """Owner -> business lookup (mirrors sms.py). Never raises."""
    try:
        result = await db.execute(
            select(Business).where(Business.owner_id == user.id)
        )
        return result.scalar_one_or_none()
    except Exception:
        return None


async def _get_campaign(
    db: AsyncSession, business_id, campaign_id: str
) -> Optional[LeadCampaign]:
    """Business-scoped campaign lookup. Never raises."""
    try:
        result = await db.execute(
            select(LeadCampaign).where(
                LeadCampaign.id == campaign_id,
                LeadCampaign.business_id == business_id,
            )
        )
        return result.scalar_one_or_none()
    except Exception:
        return None


def _in_quiet_hours_et() -> bool:
    """US Eastern quiet hours 21:00-08:00. Fail-open (False) on any error."""
    try:
        from zoneinfo import ZoneInfo

        hour = datetime.now(ZoneInfo("America/New_York")).hour
        return hour >= 21 or hour < 8
    except Exception:
        return False


async def _consent_denied(
    db: AsyncSession, business_id, member: CampaignMember
) -> bool:
    """Best-effort consent gate. ANY failure => allow (return False).

    Probes gdpr_consents (table may predate migration on some envs), then
    honours a matching Customer row with marketing_consent=False or a
    GDPR erasure flag as denial.
    """
    try:
        await db.execute(select(GdprConsent.id).limit(1))
        phone = (member.phone or "").strip()
        if phone:
            result = await db.execute(
                select(Customer)
                .where(
                    Customer.business_id == business_id,
                    Customer.phone == phone,
                )
                .limit(1)
            )
            customer = result.scalar_one_or_none()
            if customer is not None and (
                customer.gdpr_erasure_requested
                or customer.marketing_consent is False
            ):
                return True
        return False
    except Exception:
        return False


@router.post("/")
async def create_campaign(
    data: CampaignCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a campaign header. Never 500."""
    try:
        kind = (data.kind or "").strip()
        if kind not in ALLOWED_KINDS:
            raise HTTPException(
                status_code=422,
                detail=f"kind must be one of {list(ALLOWED_KINDS)}",
            )
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        campaign = LeadCampaign(
            business_id=business.id,
            name=(data.name or "").strip(),
            kind=kind,
            status="active",
        )
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        return {
            "ok": True,
            "id": str(campaign.id),
            "business_id": str(business.id),
            "name": campaign.name,
            "kind": campaign.kind,
            "status": campaign.status,
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)[:300]}


@router.post("/{campaign_id}/import")
async def import_members(
    campaign_id: str,
    data: ImportBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-import members. Phone required; dupes by phone within the
    campaign (incl. within-batch) are skipped. Never 500."""
    try:
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        campaign = await _get_campaign(db, business.id, campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaign not found")

        result = await db.execute(
            select(CampaignMember.phone).where(
                CampaignMember.campaign_id == campaign.id,
                CampaignMember.business_id == business.id,
            )
        )
        seen = {(row[0] or "").strip() for row in result.all() if (row[0] or "").strip()}

        imported = 0
        skipped = 0
        for member in (data.members or [])[:IMPORT_CAP]:
            try:
                phone = ((member.phone or "").strip())[:20]
                if not phone or phone in seen:
                    skipped += 1
                    continue
                seen.add(phone)
                db.add(
                    CampaignMember(
                        campaign_id=campaign.id,
                        business_id=business.id,
                        name=((member.name or "").strip() or None),
                        phone=phone,
                        email=((member.email or "").strip() or None),
                        status="pending",
                        attempts=0,
                    )
                )
                imported += 1
            except Exception:
                skipped += 1
                continue
        skipped += max(0, len(data.members or []) - IMPORT_CAP)
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            return {"ok": False, "error": f"commit failed: {e}"[:300]}
        return {
            "ok": True,
            "campaign_id": str(campaign.id),
            "imported": imported,
            "skipped": skipped,
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)[:300]}


@router.get("/{campaign_id}/stats")
async def campaign_stats(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Counts by member status. Never 500."""
    try:
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        campaign = await _get_campaign(db, business.id, campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        result = await db.execute(
            select(CampaignMember.status, func.count(CampaignMember.id))
            .where(
                CampaignMember.campaign_id == campaign.id,
                CampaignMember.business_id == business.id,
            )
            .group_by(CampaignMember.status)
        )
        by_status: Dict[str, int] = {}
        total = 0
        for status, count in result.all():
            by_status[str(status or "unknown")] = int(count)
            total += int(count)
        return {
            "ok": True,
            "campaign_id": str(campaign.id),
            "total": total,
            "by_status": by_status,
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@router.post("/{campaign_id}/run-step")
async def run_step(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Process up to 25 pending members: consent-gated, ET quiet-hours
    aware (21:00-08:00 -> skip, leave pending), else mark contacted
    (queued) + attempts+1 + best-effort sms_logs row. No real SMS is sent.
    Returns {processed, booked: 0, skipped}. Never 500."""
    try:
        business = await _get_business(db, current_user)
        if business is None:
            raise HTTPException(status_code=404, detail="No business found")
        campaign = await _get_campaign(db, business.id, campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaign not found")

        result = await db.execute(
            select(CampaignMember)
            .where(
                CampaignMember.campaign_id == campaign.id,
                CampaignMember.business_id == business.id,
                CampaignMember.status == "pending",
            )
            .order_by(CampaignMember.created_at)
            .limit(RUN_STEP_LIMIT)
        )
        pending = list(result.scalars().all())

        batch_ref = _make_lead_reference()
        quiet = _in_quiet_hours_et()
        now = datetime.utcnow()
        processed = 0
        skipped = 0
        touched: List[CampaignMember] = []
        for member in pending:
            try:
                if (member.status or "") != "pending":
                    skipped += 1
                    continue
                if (member.status or "") == "opted_out":
                    skipped += 1
                    continue
                if quiet:
                    skipped += 1  # leave pending
                    continue
                if await _consent_denied(db, business.id, member):
                    skipped += 1
                    continue
                member.status = "contacted"
                member.attempts = (member.attempts or 0) + 1
                member.last_contact_at = now
                touched.append(member)
                processed += 1
            except Exception:
                skipped += 1
                continue

        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            return {
                "ok": False,
                "error": f"commit failed: {e}"[:300],
                "processed": 0,
                "booked": 0,
                "skipped": len(pending),
            }

        # Best-effort sms_logs (queued only). Logging failures must not
        # undo the member updates committed above.
        try:
            for member in touched:
                try:
                    first = ((member.name or "").strip().split() or ["there"])[0]
                    db.add(
                        SmsLog(
                            business_id=business.id,
                            to_phone=member.phone or "",
                            message=(
                                f"[{batch_ref}] Hi {first}, it's Allo — "
                                "just checking back in. Reply YES to book, "
                                "STOP to opt out."
                            ),
                            status="queued",
                        )
                    )
                except Exception:
                    continue
            await db.commit()
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

        return {
            "ok": True,
            "campaign_id": str(campaign.id),
            "batch_ref": batch_ref,
            "processed": processed,
            "booked": 0,
            "skipped": skipped,
            "quiet_hours_et": quiet,
            "message": (
                "Queued only — no SMS was sent "
                "(Twilio credentials blanked in this build)."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "error": str(e)[:300],
            "processed": 0,
            "booked": 0,
            "skipped": 0,
        }
