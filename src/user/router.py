from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database.client import get_db
from src.database.models import User
from src.common import security
from src.auth.dependencies import get_current_token_payload

# Import the schemas from both domains
from src.auth import schemas as auth_schemas
from src.user import schemas as user_schemas

router = APIRouter(
    prefix="/v1/users", 
    tags=["User Profile Management"],
    dependencies=[Depends(get_current_token_payload)] # 🔒 Zero-Trust Lock
)

@router.get("/me", response_model=auth_schemas.UserResponse)
async def get_my_profile(
    token_payload: dict = Depends(get_current_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """GET: Fetch the logged-in user's details."""
    email = token_payload.get("sub")
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return user

@router.put("/me", response_model=auth_schemas.UserResponse)
async def update_my_profile(
    payload: user_schemas.UserUpdate,
    token_payload: dict = Depends(get_current_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """PUT: Update the logged-in user's general details."""
    email = token_payload.get("sub")
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.full_name = payload.full_name
    await db.commit()
    await db.refresh(user)
    
    return user

@router.post("/me/change-password", response_model=dict)
async def change_my_password(
    payload: user_schemas.ChangePasswordRequest,
    token_payload: dict = Depends(get_current_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """POST: Execute the action of changing the user's password."""
    email = token_payload.get("sub")
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if not security.verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
        
    user.hashed_password = security.get_password_hash(payload.new_password)
    await db.commit()
    
    return {"message": "Password updated successfully."}