from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.models.models import User, Business, BusinessRole, UserRole
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/rbac", tags=["rbac"])


@router.get("/roles")
async def list_roles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all roles for the business"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    roles_result = await db.execute(
        select(BusinessRole).where(BusinessRole.business_id == business.id)
    )
    return [
        {
            "id": str(r.id),
            "user_id": str(r.user_id),
            "role": r.role.value if hasattr(r.role, 'value') else r.role,
            "permissions": r.permissions,
        }
        for r in roles_result.scalars().all()
    ]


@router.post("/assign")
async def assign_role(
    user_id: UUID,
    role: str,
    permissions: list[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Assign a role to a user"""
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    role_enum = UserRole(role)
    existing = await db.execute(
        select(BusinessRole).where(
            BusinessRole.business_id == business.id,
            BusinessRole.user_id == user_id,
        )
    )
    existing_role = existing.scalar_one_or_none()

    if existing_role:
        existing_role.role = role_enum
        existing_role.permissions = permissions or []
    else:
        new_role = BusinessRole(
            business_id=business.id,
            user_id=user_id,
            role=role_enum,
            permissions=permissions or [],
        )
        db.add(new_role)

    await db.commit()
    return {"message": f"Role {role} assigned"}


@router.get("/permissions")
async def list_permissions():
    """List all available permissions"""
    return {
        "permissions": [
            "jobs.view", "jobs.create", "jobs.edit", "jobs.delete", "jobs.assign",
            "customers.view", "customers.create", "customers.edit", "customers.delete",
            "quotes.view", "quotes.create", "quotes.edit", "quotes.delete",
            "invoices.view", "invoices.create", "invoices.edit", "invoices.delete",
            "payments.view", "payments.process",
            "reports.view", "reports.export",
            "settings.view", "settings.edit",
            "team.view", "team.manage",
            "integrations.manage",
        ]
    }


@router.get("/check/{permission}")
async def check_permission(
    permission: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check if current user has a permission"""
    if current_user.role in [UserRole.OWNER, UserRole.ADMIN]:
        return {"allowed": True}

    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return {"allowed": False}

    role_result = await db.execute(
        select(BusinessRole).where(
            BusinessRole.business_id == business.id,
            BusinessRole.user_id == current_user.id,
        )
    )
    role = role_result.scalar_one_or_none()
    if role and permission in (role.permissions or []):
        return {"allowed": True}

    return {"allowed": False}
