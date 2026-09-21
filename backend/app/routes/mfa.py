import pyotp
import qrcode
import io
import base64
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import User
from app.routes.auth import get_current_user
from app.services.auth import verify_password

router = APIRouter(prefix="/api/mfa", tags=["mfa"])
settings = get_settings()


@router.post("/setup")
async def setup_mfa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate TOTP secret and QR code for MFA setup"""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="Allo"
    )

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()

    # Generate backup codes
    backup_codes = [pyotp.random_base32()[:8] for _ in range(10)]

    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_b64}",
        "provisioning_uri": provisioning_uri,
        "backup_codes": backup_codes,
    }


@router.post("/verify")
async def verify_mfa_setup(
    code: str,
    secret: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Verify TOTP code and enable MFA"""
    totp = pyotp.TOTP(secret)
    if totp.verify(code, valid_window=1):
        current_user.mfa_enabled = True
        current_user.mfa_secret = secret
        await db.commit()
        return {"success": True, "message": "MFA enabled"}
    raise HTTPException(status_code=400, detail="Invalid code")


@router.post("/verify-login")
async def verify_mfa_login(
    email: str,
    code: str,
    db: AsyncSession = Depends(get_db)
):
    """Verify MFA during login"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA not configured")

    totp = pyotp.TOTP(user.mfa_secret)
    if totp.verify(code, valid_window=1):
        return {"verified": True}
    raise HTTPException(status_code=400, detail="Invalid MFA code")


@router.delete("/disable")
async def disable_mfa(
    password: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Disable MFA (requires password confirmation)"""
    if not verify_password(password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid password")

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_backup_codes = None
    await db.commit()
    return {"success": True, "message": "MFA disabled"}


@router.post("/regenerate-backup-codes")
async def regenerate_backup_codes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Regenerate MFA backup codes"""
    if not current_user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA not enabled")

    backup_codes = [pyotp.random_base32()[:8] for _ in range(10)]
    current_user.mfa_backup_codes = backup_codes
    await db.commit()
    return {"backup_codes": backup_codes}
