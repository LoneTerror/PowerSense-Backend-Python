from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from src.auth.dependencies import get_current_token_payload
from src.database.client import get_db
from src.database.models import User
from src.device.schemas import RelayConfigUpdate, RelayToggle, RelayConfigResponse
from src.device import service

router = APIRouter(
    prefix="/v1/relays",
    tags=["Device Management"],
    dependencies=[Depends(get_current_token_payload)]
)

# Resolves the exact user ID making the request
async def get_current_user_id(
    token_payload: dict = Depends(get_current_token_payload), 
    db: AsyncSession = Depends(get_db)
) -> int:
    email = token_payload.get("sub")
    query = select(User.id).where(User.email == email)
    user_id = (await db.execute(query)).scalar_one_or_none()
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")
    return user_id

@router.get("/config", response_model=List[RelayConfigResponse])
async def get_relay_config(user_id: int = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    """Get detailed metadata ONLY for the logged-in user's relays"""
    # Updated `service.get_all_configs` to accept user_id and filter using: select(RelayConfig).where(RelayConfig.owner_id == user_id)
    return await service.get_all_configs(user_id, db)

@router.post("/{relay_id}/config")
async def update_relay_config(
    relay_id: int, 
    payload: RelayConfigUpdate, 
    user_id: int = Depends(get_current_user_id), 
    db: AsyncSession = Depends(get_db)
):
    """Update names/descriptions from App/Web"""
    # Updated `service.update_config` to ensure the relay belongs to user_id before updating
    return await service.update_config(relay_id, user_id, payload, db)

@router.post("/{relay_id}/toggle")
async def toggle_relay(
    relay_id: int, 
    payload: RelayToggle, 
    user_id: int = Depends(get_current_user_id), 
    db: AsyncSession = Depends(get_db)
):
    """Standard Toggle Endpoint (Logs activity to DB)"""
    # Updated `service.log_relay_toggle` to ensure the relay belongs to user_id before toggling
    await service.log_relay_toggle(relay_id, user_id, payload.state, db)
    return {"success": True, "newState": payload.state}

@router.delete("/{relay_id}")
async def delete_relay(
    relay_id: int, 
    user_id: int = Depends(get_current_user_id), 
    db: AsyncSession = Depends(get_db)
):
    """Delete a switch/relay from App/Web"""
    result = await service.delete_config(relay_id, user_id, db)
    
    # If the service failed (e.g., wrong user or bad ID), returns proper 404 Error to Android
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
        
    # Returns the clean confirmation to Android
    return {"detail": result["message"]}