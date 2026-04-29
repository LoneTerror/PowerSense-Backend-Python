from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from shared.powersense_db.database import get_db
from shared.powersense_db.models.relay import RelayConfig, RelayLog
# In a production environment, this service would communicate with the WS manager 
# via a message broker (Redis/Kafka) to trigger the hardware switch.

router = APIRouter()

class RelayConfigUpdate(BaseModel):
    name: str
    description: str

class RelayToggle(BaseModel):
    state: bool

@router.get("/config")
async def get_relay_config(db: AsyncSession = Depends(get_db)):
    """Get detailed metadata for all relays"""
    query = select(RelayConfig).order_by(RelayConfig.id.asc()) # Replaces raw SELECT 
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/{relay_id}/config")
async def update_relay_config(relay_id: int, payload: RelayConfigUpdate, db: AsyncSession = Depends(get_db)):
    """Update names/descriptions from App/Web"""
    query = select(RelayConfig).where(RelayConfig.id == relay_id)
    result = await db.execute(query)
    relay = result.scalar_one_or_none()
    
    if relay:
        relay.name = payload.name
        relay.description = payload.description
    else:
        new_relay = RelayConfig(id=relay_id, name=payload.name, description=payload.description)
        db.add(new_relay)
        
    await db.commit()
    return {"success": True, "message": f"Relay {relay_id} updated"}

@router.post("/{relay_id}/toggle")
async def toggle_relay(relay_id: int, payload: RelayToggle, db: AsyncSession = Depends(get_db)):
    """Standard Toggle Endpoint (Used by Android)"""
    # 1. Publish command to Message Broker (which Telemetry WS Manager listens to)
    # 2. Log activity to database, replacing logRelayActivity
    
    action_log = RelayLog(
        relay_id=relay_id,
        state=payload.state,
        action_by="App/Web"
    )
    db.add(action_log)
    await db.commit()
    
    return {"success": True, "newState": payload.state}