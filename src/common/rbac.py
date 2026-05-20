from fastapi import Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.client import get_db
from src.database.models import User, RolePolicy
from src.auth.dependencies import get_current_token_payload

async def verify_endpoint_access(
    request: Request,
    token_payload: dict = Depends(get_current_token_payload),
    db: AsyncSession = Depends(get_db)
):
    email = token_payload.get("sub")
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled or not found.")

    # 1. Master Override: Admins can access everything unconditionally
    if user.role == "admin":
        return user

    current_path = request.url.path
    cleaned_path = current_path.replace("/powersense", "") 

    # 2. Check Personal Specific Clearance
    if cleaned_path in user.allowed_endpoints:
        return user

    # 3. Check Role-Based Clearance (The Upgrade)
    role_query = select(RolePolicy).where(RolePolicy.name == user.role)
    role_result = await db.execute(role_query)
    role_policy = role_result.scalar_one_or_none()

    if role_policy and cleaned_path in role_policy.allowed_endpoints:
        return user

    # 4. If neither personal nor role clearance exists, block the request
    raise HTTPException(
        status_code=403, 
        detail=f"RBAC Violation: Role '{user.role}' lacks clearance for {cleaned_path}"
    )

async def require_admin(user: User = Depends(verify_endpoint_access)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Strictly Admin access required.")
    return user