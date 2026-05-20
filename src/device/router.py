from fastapi import APIRouter, Depends, HTTPException
from src.auth.dependencies import get_current_token_payload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from src.database.client import get_db
from src.device.schemas import RelayConfigUpdate, RelayToggle, RelayConfigResponse
from src.device import service

router = APIRouter(
    prefix="/v1/relays",
    tags=["Device Management"],
    dependencies=[Depends(get_current_token_payload)] # THIS LOCKS EVERY ROUTE, UNLOCKS ONLY WHEN THE TOKEN IS PASSED
)

@router.get("/config", response_model=List[RelayConfigResponse])
async def get_relay_config(db: AsyncSession = Depends(get_db)):
    """Get detailed metadata for all relays"""
    return await service.get_all_configs(db)

@router.post("/{relay_id}/config")
async def update_relay_config(relay_id: int, payload: RelayConfigUpdate, db: AsyncSession = Depends(get_db)):
    """Update names/descriptions from App/Web"""
    return await service.update_config(relay_id, payload, db)

@router.post("/{relay_id}/toggle")
async def toggle_relay(relay_id: int, payload: RelayToggle, db: AsyncSession = Depends(get_db)):
    """Standard Toggle Endpoint (Logs activity to DB)"""
    # Note: In a fully decoupled system, this endpoint publishes to an event bus (like Redis Pub/Sub)
    # The Telemetry service listens to that bus and forwards the command to the ESP8266 via WebSocket.
    await service.log_relay_toggle(relay_id, payload.state, db)
    return {"success": True, "newState": payload.state}