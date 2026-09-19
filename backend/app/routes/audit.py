from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import AuditLog, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/audit", tags=["audit"])


async def log_audit(
    db: AsyncSession,
    business_id: UUID,
    user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID = None,
    old_values: dict = None,
    new_values: dict = None,
    ip_address: str = None,
):
    """Log an audit event"""
    log = AuditLog(
        business_id=business_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
    )
    db.add(log)
    await db.flush()


@router.get("/logs")
async def list_audit_logs(
    entity_type: str = None,
    entity_id: UUID = None,
    action: str = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List audit logs with filters"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    query = select(AuditLog).where(AuditLog.business_id == business.id)

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)

    query = query.order_by(AuditLog.created_at.desc()).limit(limit)
    logs_result = await db.execute(query)

    return [
        {
            "id": str(log.id),
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": str(log.entity_id) if log.entity_id else None,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "user_id": str(log.user_id) if log.user_id else None,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs_result.scalars().all()
    ]


@router.get("/entity/{entity_type}/{entity_id}")
async def get_entity_history(
    entity_type: str,
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get full history for a specific entity"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    logs_result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.business_id == business.id,
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )
        .order_by(AuditLog.created_at.asc())
    )

    return [
        {
            "id": str(log.id),
            "action": log.action,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs_result.scalars().all()
    ]
