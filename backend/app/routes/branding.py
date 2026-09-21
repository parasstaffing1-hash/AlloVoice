"""White-label / multi-brand settings for VoiceField (UK field service SaaS)."""
import base64
import copy
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.routes.auth import get_current_user
from app.services import storage as r2

router = APIRouter(prefix="/api/branding", tags=["branding"])

# ── In-memory store keyed by business id (production → database + R2) ────
BRAND_KITS: dict[str, dict] = {}

HEX_COLOUR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
LOGO_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|jpg|svg\+xml);base64,[A-Za-z0-9+/=\s]+$")
LOGO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg")


def _default_kit() -> dict:
    return {
        "brand_name": "VoiceField",
        "logo_url": None,
        "primary_color": "#f97316",
        "secondary_color": "#1e293b",
        "accent_color": "#fbbf24",
        "font_family": "Inter, system-ui, sans-serif",
        "email_footer": "",
        "portal_subdomain": None,
        "custom_domain": None,
        "favicon_url": None,
        "powered_by_visible": True,
        "avatar_glb_url": None,
        "avatar_voice": "sonia",
    }


def _business_key(user) -> str:
    # NOTE: must not touch user.business — lazy relationship access raises
    # MissingGreenlet under async SQLAlchemy. user.id is a loaded column.
    return f"user:{user.id}"


def _get_kit(key: str) -> dict:
    if key not in BRAND_KITS:
        BRAND_KITS[key] = _default_kit()
    return BRAND_KITS[key]


def _validate_hex(field_name: str, value: Optional[str]) -> None:
    if value is not None and not HEX_COLOUR_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid hex colour for {field_name}: {value}",
        )


# ── Schemas ──────────────────────────────────────────────────────────────
class BrandKitUpdate(BaseModel):
    brand_name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    font_family: Optional[str] = None
    email_footer: Optional[str] = None
    portal_subdomain: Optional[str] = None
    custom_domain: Optional[str] = None
    favicon_url: Optional[str] = None
    powered_by_visible: Optional[bool] = None
    avatar_glb_url: Optional[str] = None
    avatar_voice: Optional[str] = None


class LogoUpload(BaseModel):
    logo_base64: str = Field(description="Image data URL (png/jpeg/svg)")
    filename: str


# ── Get current brand kit ────────────────────────────────────────────────
@router.get("")
async def get_branding(current_user=Depends(get_current_user)):
    """Return the current business brand kit."""
    return copy.deepcopy(_get_kit(_business_key(current_user)))


# ── Update brand kit ─────────────────────────────────────────────────────
@router.put("")
async def update_branding(
    data: BrandKitUpdate,
    current_user=Depends(get_current_user),
):
    """Partially update the brand kit; validates hex colours."""
    kit = _get_kit(_business_key(current_user))
    updates = data.model_dump(exclude_unset=True)
    for colour_field in ("primary_color", "secondary_color", "accent_color"):
        if colour_field in updates:
            _validate_hex(colour_field, updates[colour_field])
    if "avatar_glb_url" in updates and updates["avatar_glb_url"] is not None:
        if not updates["avatar_glb_url"].startswith("https://"):
            raise HTTPException(
                status_code=400,
                detail="avatar_glb_url must start with https://",
            )
    if "avatar_voice" in updates and updates["avatar_voice"] is not None:
        if updates["avatar_voice"] not in ("sonia", "ryan", "default"):
            raise HTTPException(
                status_code=400,
                detail="avatar_voice must be one of: sonia, ryan, default",
            )
    for key, value in updates.items():
        kit[key] = value
    return copy.deepcopy(kit)


# ── Upload logo ──────────────────────────────────────────────────────────
@router.post("/logo")
async def upload_logo(
    data: LogoUpload,
    current_user=Depends(get_current_user),
):
    """Store a logo image data URL (production → R2 object storage)."""
    if not LOGO_DATA_URL_RE.match(data.logo_base64.strip()):
        raise HTTPException(
            status_code=400,
            detail="logo_base64 must be a valid image data URL (png/jpeg/svg)",
        )
    lowered = data.filename.lower()
    if not lowered.endswith(LOGO_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="filename must end with .png, .jpg, .jpeg or .svg",
        )
    kit = _get_kit(_business_key(current_user))
    # Legacy local behaviour fallback.
    logo_url = f"stored:{_business_key(current_user)}/{data.filename}"
    try:
        if r2.is_configured():
            raw = data.logo_base64.strip()
            header, _, b64data = raw.partition(",")
            header_lower = header.lower()
            if "svg" in header_lower:
                ext, content_type = ".svg", "image/svg+xml"
            elif "png" in header_lower:
                ext, content_type = ".png", "image/png"
            else:
                ext, content_type = ".jpg", "image/jpeg"
            logo_bytes = base64.b64decode("".join(b64data.split()))
            # Keyed by user id (see _business_key) — never touch the lazy
            # user.business relationship under async SQLAlchemy.
            business_id = str(current_user.id)
            key = f"branding/{business_id}/logo{ext}"
            r2.upload_bytes(key, logo_bytes, content_type)
            logo_url = r2.file_url(key)
    except Exception:
        pass
    kit["logo_url"] = logo_url
    return {"logo_url": logo_url}


# ── Public portal theme ──────────────────────────────────────────────────
@router.get("/portal-theme")
async def get_portal_theme(subdomain: Optional[str] = Query(default=None)):
    """Public theme lookup for the customer portal by subdomain."""
    if subdomain:
        for kit in BRAND_KITS.values():
            if kit.get("portal_subdomain") == subdomain:
                theme = copy.deepcopy(kit)
                return {
                    "brand_name": theme.get("brand_name"),
                    "primary_color": theme.get("primary_color"),
                    "secondary_color": theme.get("secondary_color"),
                    "accent_color": theme.get("accent_color"),
                    "logo_url": theme.get("logo_url"),
                    "favicon_url": theme.get("favicon_url"),
                    "font_family": theme.get("font_family"),
                    "avatar_glb_url": theme.get("avatar_glb_url"),
                    "avatar_voice": theme.get("avatar_voice"),
                }
    defaults = _default_kit()
    return {
        "brand_name": defaults["brand_name"],
        "primary_color": defaults["primary_color"],
        "secondary_color": defaults["secondary_color"],
        "accent_color": defaults["accent_color"],
        "logo_url": defaults["logo_url"],
        "favicon_url": defaults["favicon_url"],
        "font_family": defaults["font_family"],
        "avatar_glb_url": defaults["avatar_glb_url"],
        "avatar_voice": defaults["avatar_voice"],
    }


# ── Reset to defaults ────────────────────────────────────────────────────
@router.post("/reset")
async def reset_branding(current_user=Depends(get_current_user)):
    """Reset the brand kit to VoiceField defaults."""
    BRAND_KITS[_business_key(current_user)] = _default_kit()
    return copy.deepcopy(BRAND_KITS[_business_key(current_user)])
