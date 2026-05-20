from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import urllib.request
import json
import asyncio

from src.database.client import get_db
from src.database.models import User, RolePolicy
from src.user import schemas
from src.common import security
from src.common.rbac import require_admin

router = APIRouter(
    prefix="/v1/admin", 
    tags=["Admin User Management"],
    dependencies=[Depends(require_admin)] 
)

# ==========================================
# 1. USER MANAGEMENT ROUTES
# ==========================================

@router.get("/users", response_model=list[schemas.AdminUserResponse])
async def get_all_users(db: AsyncSession = Depends(get_db)):
    """GET: List all registered profiles in the grid."""
    query = select(User)
    result = await db.execute(query)
    users = result.scalars().all()
    
    # HOTFIX: Convert legacy NULL values to empty lists so Pydantic doesn't crash
    for u in users:
        if u.allowed_endpoints is None:
            u.allowed_endpoints = []
            
    return users

@router.post("/users", response_model=schemas.AdminUserResponse)
async def create_user_manually(
    payload: schemas.AdminUserCreate, 
    db: AsyncSession = Depends(get_db)
):
    """POST: Manually provision a new user with specific clearance."""
    query = select(User).where(User.email == payload.email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered.")

    new_user = User(
        email=payload.email,
        hashed_password=security.get_password_hash(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        allowed_endpoints=payload.allowed_endpoints
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@router.put("/users/{user_id}", response_model=schemas.AdminUserResponse)
async def update_user_access(
    user_id: int, 
    payload: schemas.AdminUserUpdate, 
    db: AsyncSession = Depends(get_db)
):
    """PUT: Update roles, activity status, or endpoint permissions for a user."""
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.allowed_endpoints is not None:
        user.allowed_endpoints = payload.allowed_endpoints

    await db.commit()
    await db.refresh(user)
    return user

# ==========================================
# 2. SYSTEM ENDPOINT DISCOVERY
# ==========================================

def fetch_openapi(url: str):
    """Synchronous function to fetch JSON from a URL."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as response:
            return json.loads(response.read().decode())
    except Exception:
        return None

@router.get("/system-routes")
async def get_all_system_routes():
    """GET: Scrapes the entire cluster and returns all available endpoints and descriptions."""
    
    # Define your microservice cluster map
    services = {
        "Auth Service": "http://127.0.0.1:8000/openapi.json",
        "Device Service": "http://127.0.0.1:8001/openapi.json",
        "Telemetry Service": "http://127.0.0.1:8002/openapi.json",
        "User Service": "http://127.0.0.1:8003/openapi.json"
    }
    
    master_route_list = []
    
    for service_name, url in services.items():
        # Fetch each service's documentation asynchronously 
        openapi_data = await asyncio.to_thread(fetch_openapi, url)
        
        if not openapi_data:
            master_route_list.append({
                "service": service_name,
                "status": "Offline / Unreachable"
            })
            continue
            
        paths = openapi_data.get("paths", {})
        
        for path, methods in paths.items():
            for method, details in methods.items():
                master_route_list.append({
                    "service": service_name,
                    "method": method.upper(),
                    "path": path,
                    "summary": details.get("summary", "No description provided.")
                })
                
    return {"cluster_routes": master_route_list}


# ==========================================
# 3. ROLE POLICY MANAGEMENT
# ==========================================


@router.get("/roles", response_model=list[schemas.RolePolicyResponse])
async def get_all_roles(db: AsyncSession = Depends(get_db)):
    """GET: List all roles and their assigned endpoint permissions."""
    query = select(RolePolicy)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/roles", response_model=schemas.RolePolicyResponse)
async def create_new_role(
    payload: schemas.RolePolicyCreate, 
    db: AsyncSession = Depends(get_db)
):
    """POST: Create a brand new role (e.g., 'operator', 'auditor')."""
    query = select(RolePolicy).where(RolePolicy.name == payload.name)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role policy already exists.")

    new_policy = RolePolicy(
        name=payload.name,
        allowed_endpoints=payload.allowed_endpoints
    )
    db.add(new_policy)
    await db.commit()
    await db.refresh(new_policy)
    return new_policy

@router.put("/roles/{role_name}", response_model=schemas.RolePolicyResponse)
async def update_role_endpoints(
    role_name: str, 
    payload: schemas.RolePolicyUpdate, 
    db: AsyncSession = Depends(get_db)
):
    """PUT: Update the allowed endpoints array for a specific role."""
    query = select(RolePolicy).where(RolePolicy.name == role_name)
    result = await db.execute(query)
    policy = result.scalar_one_or_none()

    if not policy:
        # If the role doesn't exist yet, seamlessly create it
        policy = RolePolicy(name=role_name, allowed_endpoints=payload.allowed_endpoints)
        db.add(policy)
    else:
        policy.allowed_endpoints = payload.allowed_endpoints

    await db.commit()
    await db.refresh(policy)
    return policy