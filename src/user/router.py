import os
import shutil
import uuid
from fastapi import UploadFile, File
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database.client import get_db
from src.database.models import User
from src.common import security
from src.auth.dependencies import get_current_token_payload

# Import the email triggers
from src.common.email_utils import send_profile_update_email, send_password_changed_email

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
    request: Request,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(get_current_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """PUT: Update the logged-in user's general details and fire notification."""
    email = token_payload.get("sub")
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.full_name = payload.full_name
    await db.commit()
    await db.refresh(user)
    
    # Extract True Device IP from Nginx Reverse Proxy Header
    client_ip = request.headers.get("X-Real-IP", request.client.host)

    # Dispatch the Resend email off the main thread to prevent Android UI lag
    background_tasks.add_task(
        send_profile_update_email,
        to_email=user.email,
        full_name=user.full_name,
        ip_address=client_ip
    )
    
    return user

@router.post("/me/change-password", response_model=dict)
async def change_my_password(
    payload: user_schemas.ChangePasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(get_current_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """POST: Execute password change and trigger critical security alert."""
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
    
    # Extract True Device IP from Nginx Reverse Proxy Header
    client_ip = request.headers.get("X-Real-IP", request.client.host)

    # Dispatch the Resend email off the main thread
    background_tasks.add_task(
        send_password_changed_email,
        to_email=user.email,
        full_name=user.full_name,
        ip_address=client_ip
    )
    
    return {"message": "Password updated successfully."}


# Create a local directory inside the Docker container to store images
UPLOAD_DIR = "static/avatars"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/me/avatar", response_model=dict)
async def upload_profile_picture(
    file: UploadFile = File(...),
    token_payload: dict = Depends(get_current_token_payload),
    db: AsyncSession = Depends(get_db)
):
    """POST: Securely upload and store a profile picture."""
    # 1. Validate it is actually an image
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Images only.")

    # 2. Generate a random UUID filename (prevents users from overwriting each other's files)
    file_extension = file.filename.split(".")[-1]
    secure_filename = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, secure_filename)

    # 3. Stream the file to the hard drive
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 4. Construct the URL that Android will use to download it
    # We route this through the existing /v1/users/ Nginx block!
    public_url = f"https://backend.powersense.top/v1/users/static/avatars/{secure_filename}"

    # 5. Save the URL to the Database
    email = token_payload.get("sub")
    query = select(User).where(User.email == email)
    user = (await db.execute(query)).scalar_one()
    
    user.avatar_url = public_url
    await db.commit()

    return {"message": "Avatar updated successfully", "avatar_url": public_url}