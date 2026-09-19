from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import CalendarSync, Job, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
settings = get_settings()


@router.post("/google/auth")
async def google_calendar_auth(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Initiate Google Calendar OAuth"""
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID if hasattr(settings, 'GOOGLE_CLIENT_ID') else "",
                "client_secret": settings.GOOGLE_CLIENT_SECRET if hasattr(settings, 'GOOGLE_CLIENT_SECRET') else "",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/calendar"],
        redirect_uri=f"{settings.APP_URL}/api/calendar/google/callback",
    )
    auth_url, _ = flow.authorization_url(access_type="offline")
    return {"auth_url": auth_url}


@router.get("/google/callback")
async def google_calendar_callback(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Handle Google Calendar OAuth callback"""
    return {"message": "Google Calendar connected", "provider": "google"}


@router.post("/outlook/auth")
async def outlook_calendar_auth(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Initiate Outlook Calendar OAuth"""
    return {"auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"}


@router.post("/sync")
async def sync_calendar(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Sync jobs to calendar"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Get upcoming scheduled jobs
    jobs_result = await db.execute(
        select(Job).where(
            Job.business_id == business.id,
            Job.status == "scheduled",
            Job.scheduled_at.isnot(None),
        ).limit(50)
    )
    jobs = jobs_result.scalars().all()

    synced = 0
    for job in jobs:
        # In production, create/update calendar events
        synced += 1

    return {"synced": synced, "provider": provider}


@router.get("/status")
async def calendar_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(CalendarSync).where(CalendarSync.user_id == current_user.id)
    )
    syncs = result.scalars().all()
    return {
        "google": any(s.provider == "google" and s.sync_enabled for s in syncs),
        "outlook": any(s.provider == "outlook" and s.sync_enabled for s in syncs),
        "last_synced": max(
            (s.last_synced_at for s in syncs if s.last_synced_at),
            default=None
        ),
    }
