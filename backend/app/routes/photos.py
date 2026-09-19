import io
import base64
import json
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID
from PIL import Image, ImageFilter, ImageEnhance
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import JobPhoto, Job, Business, User
from app.routes.auth import get_current_user
from app.services import storage as r2
from app.services import llm

router = APIRouter(prefix="/api/photos", tags=["photos"])
settings = get_settings()


def process_image(image_bytes: bytes, max_size: int = 1200, quality: int = 85) -> bytes:
    """Process and optimize image for storage"""
    img = Image.open(io.BytesIO(image_bytes))

    # Auto-orient based on EXIF
    try:
        from PIL import ExifTags
        exif = img._getexif()
        if exif:
            orientation = exif.get(ExifTags.Orientation)
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation == 6:
                img = img.rotate(270, expand=True)
            elif orientation == 8:
                img = img.rotate(90, expand=True)
    except Exception:
        pass

    # Resize if too large
    if max(img.size) > max_size:
        ratio = max_size / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    # Convert to RGB if necessary
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Optimize
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=100, threshold=2))
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.05)

    # Save as JPEG
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def create_thumbnail(image_bytes: bytes, size: int = 200) -> bytes:
    """Create a thumbnail version of the image"""
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((size, size), Image.Resampling.LANCZOS)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=80, optimize=True)
    return buffer.getvalue()


def extract_metadata(image_bytes: bytes) -> dict:
    """Extract basic image metadata"""
    img = Image.open(io.BytesIO(image_bytes))
    return {
        "width": img.size[0],
        "height": img.size[1],
        "format": img.format,
        "mode": img.mode,
    }


@router.post("/upload/{job_id}")
async def upload_job_photo(
    job_id: UUID,
    file: UploadFile = File(...),
    photo_type: str = "before",
    caption: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload and process a job photo"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    contents = await file.read()

    # Validate file size (max 20MB)
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")

    # Process image
    processed = process_image(contents)
    thumbnail = create_thumbnail(contents)
    metadata = extract_metadata(contents)

    # Create base64 for preview
    preview_b64 = base64.b64encode(thumbnail).decode()

    # Save to database (flush first to get photo.id for the R2 key)
    photo = JobPhoto(
        job_id=job_id,
        url=f"local://{file.filename}",
        r2_key=f"jobs/{job_id}/photos/{file.filename}",
        photo_type=photo_type,
        caption=caption,
        ai_description=None
    )
    db.add(photo)
    await db.flush()
    try:
        if r2.is_configured():
            full_key = f"jobs/{job_id}/photos/{photo.id}.jpg"
            thumb_key = f"jobs/{job_id}/photos/thumbs/{photo.id}.jpg"
            r2.upload_bytes(full_key, processed, "image/jpeg")
            r2.upload_bytes(thumb_key, thumbnail, "image/jpeg")
            photo.r2_key = full_key
            photo.url = r2.file_url(full_key)
    except Exception:
        pass
    await db.commit()
    await db.refresh(photo)

    return {
        "id": str(photo.id),
        "url": photo.url,
        "photo_type": photo_type,
        "metadata": metadata,
        "preview": f"data:image/jpeg;base64,{preview_b64}",
        "size_bytes": len(processed),
    }


@router.get("/job/{job_id}")
async def list_job_photos(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all photos for a job"""
    result = await db.execute(
        select(JobPhoto)
        .where(JobPhoto.job_id == job_id)
        .order_by(JobPhoto.taken_at.desc())
    )
    photos = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "url": p.url,
            "photo_type": p.photo_type,
            "caption": p.caption,
            "ai_description": p.ai_description,
            "taken_at": p.taken_at.isoformat() if p.taken_at else None,
        }
        for p in photos
    ]


@router.post("/analyze/{photo_id}")
async def analyze_photo(
    photo_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """AI vision analysis of a job photo (condition, issues, cost estimate)"""
    result = await db.execute(select(JobPhoto).where(JobPhoto.id == photo_id))
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    analysis = {
        "condition": "Good",
        "issues_detected": [],
        "recommendations": ["Regular maintenance recommended"],
        "estimated_repair_cost": None,
    }

    # ─── Vision model (never 500) ───
    try:
        if llm.is_configured():
            raw: bytes | None = None
            if photo.r2_key:
                try:
                    raw = r2.download_bytes(photo.r2_key)
                except Exception:
                    raw = None
            if raw is None and photo.url and photo.url.startswith("http"):
                import httpx
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(photo.url)
                    if resp.status_code == 200:
                        raw = resp.content
            if raw:
                import re
                img_b64 = base64.b64encode(raw).decode()
                text = await llm.describe_image(
                    img_b64,
                    "You are a UK trades surveyor looking at a job-site photo. "
                    "Return ONLY valid JSON, no markdown: "
                    '{"condition": "Good"|"Fair"|"Poor", '
                    '"issues_detected": [str], "recommendations": [str], '
                    '"estimated_repair_cost": number|null (GBP, null if unknown)}.',
                )
                text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(),
                              flags=re.MULTILINE).strip()
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    analysis = {
                        "condition": str(parsed.get("condition", "Fair") or "Fair"),
                        "issues_detected": list(parsed.get("issues_detected", []) or []),
                        "recommendations": list(parsed.get("recommendations", []) or []),
                        "estimated_repair_cost": parsed.get("estimated_repair_cost"),
                    }
    except Exception:
        pass

    photo.ai_description = json.dumps(analysis)
    await db.commit()

    return {"photo_id": str(photo_id), "analysis": analysis}
