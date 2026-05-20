from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from src.auth.audit import process_login_audit, process_password_reset_request_audit, process_password_changed_audit
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.client import get_db
from src.database.models import User, RefreshToken
from src.auth import schemas
from src.common import security
from src.common.email_utils import send_welcome_email, send_login_alert_email
from typing import List
from src.auth.dependencies import require_admin

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])

@router.post("/signup", response_model=schemas.TokenResponse)
async def signup(
    user_data: schemas.UserCreate, 
    background_tasks: BackgroundTasks, # <-- Inject the BackgroundTasks dependency
    db: AsyncSession = Depends(get_db)
):
    # Check if user exists
    query = select(User).where(User.email == user_data.email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create User
    new_user = User(
        email=user_data.email,
        hashed_password=security.get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role="admin" if user_data.email == "chakrabortyprasun10@gmail.com" else "viewer"
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Generate Tokens
    access_token = security.create_access_token(data={"sub": new_user.email, "role": new_user.role})
    refresh_token, expires_at = security.create_refresh_token(data={"sub": new_user.email})

    # Save Refresh Token to DB
    db_refresh = RefreshToken(user_id=new_user.id, token=refresh_token, expires_at=expires_at)
    db.add(db_refresh)
    await db.commit()

    # Handing the email task off to FastAPI's background thread for new signup
    background_tasks.add_task(send_welcome_email, new_user.email, new_user.full_name)

    return {"access_token": access_token, "refresh_token": refresh_token}

@router.post("/login", response_model=schemas.TokenResponse)
async def login(
    request: Request, 
    user_data: schemas.UserLogin, 
    background_tasks: BackgroundTasks, 
    db: AsyncSession = Depends(get_db)
):
    query = select(User).where(User.email == user_data.email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user or not security.verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Extract the client IP natively
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host

    access_token = security.create_access_token(data={"sub": user.email, "role": user.role})
    refresh_token, expires_at = security.create_refresh_token(data={"sub": user.email})

    db_refresh = RefreshToken(user_id=user.id, token=refresh_token, expires_at=expires_at)
    db.add(db_refresh)
    await db.commit()

    # Hand off the entire auditing workflow to the background task
    background_tasks.add_task(process_login_audit, user.id, user.email, user.full_name, client_ip)

    return {"access_token": access_token, "refresh_token": refresh_token}\
    

@router.post("/forgot-password", response_model=dict)
async def forgot_password(
    request: Request,
    payload: schemas.ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    query = select(User).where(User.email == payload.email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    # Always return a generic success message to prevent Email Enumeration
    response_msg = {"message": "If that email exists in our system, a reset link has been sent."}

    if user:
        client_ip = request.headers.get("X-Forwarded-For", request.client.host).split(",")[0].strip()
        reset_token = security.create_reset_token(user.email)
        background_tasks.add_task(
            process_password_reset_request_audit, 
            user.id, user.email, user.full_name, client_ip, reset_token
        )

    return response_msg


@router.post("/reset-password", response_model=dict)
async def reset_password(
    request: Request,
    payload: schemas.ResetPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    # 1. Verify Token Cryptographically
    email = security.verify_reset_token(payload.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

    # 2. Find User
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # 3. Hash New Password and Save
    user.hashed_password = security.get_password_hash(payload.new_password)
    await db.commit()

    # 4. Audit the Success
    client_ip = request.headers.get("X-Forwarded-For", request.client.host).split(",")[0].strip()
    background_tasks.add_task(process_password_changed_audit, user.id, client_ip)

    return {"message": "Password has been successfully updated. You may now log in."}



@router.get("/users", response_model=List[schemas.UserResponse])
async def get_all_users(
    skip: int = 0, 
    limit: int = 100, 
    db: AsyncSession = Depends(get_db),
    # By adding this Depends(), FastAPI automatically blocks unauthorized requests
    admin_payload: dict = Depends(require_admin) 
):
    """
    Fetch all users in the system. 
    🔒 RBAC: Admin access only.
    """
    query = select(User).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()
    
    return users