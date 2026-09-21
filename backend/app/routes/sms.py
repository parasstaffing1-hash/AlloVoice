from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
import httpx
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import SmsLog, Business, User
from app.routes.auth import get_current_user
from app.services.phone import normalize_uk_phone

router = APIRouter(prefix="/api/sms", tags=["sms"])
settings = get_settings()


def _twilio_creds() -> tuple[str, str]:
    s = get_settings()
    return ((s.TWILIO_ACCOUNT_SID or "").strip(),
            (s.TWILIO_AUTH_TOKEN or "").strip())


def _twilio_from() -> str:
    s = get_settings()
    return ((s.TWILIO_PHONE_NUMBER or "").strip()
            or (s.TWILIO_SENDER_ID or "Allo").strip())


@router.post("/send")
async def send_sms(
    to_phone: str,
    message: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send SMS via Twilio (real send; logged either way)"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()

    try:
        to_e164 = normalize_uk_phone(to_phone)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UK phone number")

    sid, token = _twilio_creds()
    if not sid or not token:
        raise HTTPException(status_code=503, detail="SMS not configured (TWILIO_* missing)")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                auth=(sid, token),
                data={"To": to_e164, "From": _twilio_from(), "Body": message[:1600]},
            )
            resp.raise_for_status()
            tw_sid = resp.json().get("sid")
        log = SmsLog(
            business_id=business.id if business else None,
            to_phone=to_e164,
            message=message,
            status="sent",
            sent_at=datetime.utcnow(),
        )
        db.add(log)
        await db.commit()
        return {"success": True, "to": to_e164, "sid": tw_sid}
    except HTTPException:
        raise
    except Exception as e:
        log = SmsLog(
            business_id=business.id if business else None,
            to_phone=to_phone,
            message=message,
            status="failed",
        )
        db.add(log)
        await db.commit()
        return {"success": False, "error": str(e)[:300]}


@router.post("/send-otp")
async def send_otp(
    to_phone: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send OTP verification code"""
    import pyotp
    totp = pyotp.TOTP(pyotp.random_base32())
    code = totp.now()
    message = f"Your Allo verification code is: {code}. Valid for 5 minutes."

    return await send_sms(to_phone, message, current_user, db)


@router.get("/logs")
async def list_sms_logs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(SmsLog).order_by(SmsLog.created_at.desc()).limit(100)
    )
    return [
        {
            "id": str(log.id),
            "to": log.to_phone,
            "message": log.message[:50],
            "status": log.status,
            "created_at": log.created_at.isoformat(),
        }
        for log in result.scalars().all()
    ]
