from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import delete
from src.database.models import RelayConfig, RelayLog
from src.device.schemas import RelayConfigUpdate

async def get_all_configs(user_id: int, db: AsyncSession):
    # 🔒 SECURE: Filters the database so the user only sees THEIR devices
    query = select(RelayConfig).where(RelayConfig.owner_id == user_id).order_by(RelayConfig.id.asc())
    result = await db.execute(query)
    relays = result.scalars().all()
    
    # Convert legacy NULL device_ids to empty strings so Pydantic and Android don't crash when trying to read them.
    for relay in relays:
        if relay.device_id is None:
            relay.device_id = ""
            
    return relays

async def update_config(relay_id: int, user_id: int, payload: RelayConfigUpdate, db: AsyncSession):
    # 🔒 SECURE: Ensures the user actually owns the relay before allowing an update
    query = select(RelayConfig).where(RelayConfig.id == relay_id, RelayConfig.owner_id == user_id)
    result = await db.execute(query)
    relay = result.scalar_one_or_none()
    
    if relay:
        relay.name = payload.name
        relay.description = payload.description
        relay.device_id = payload.device_id           
        relay.physical_pin = payload.physical_pin     
        relay.threshold = payload.threshold
        relay.threshold_unit = payload.threshold_unit
    else:
        new_relay = RelayConfig(
            id=relay_id, 
            owner_id=user_id, 
            name=payload.name, 
            description=payload.description,
            device_id=payload.device_id,              
            physical_pin=payload.physical_pin,        
            threshold=payload.threshold,
            threshold_unit=payload.threshold_unit
        )
        db.add(new_relay)
        
    await db.commit()
    return {"success": True, "message": f"Relay {relay_id} updated"}

async def log_relay_toggle(relay_id: int, user_id: int, state: bool, db: AsyncSession):
    # 📝 AUDIT TRAIL: Logs exactly which user turned the switch on/off
    action_log = RelayLog(
        relay_id=relay_id,
        state=state,
        action_by=f"User {user_id}" 
    )
    db.add(action_log)
    await db.commit()


async def delete_config(relay_id: int, user_id: int, db: AsyncSession):
    # Firstly, check if the relay actually exists AND belongs to the user
    check_stmt = select(RelayConfig).where(RelayConfig.id == relay_id, RelayConfig.owner_id == user_id)
    result = await db.execute(check_stmt)
    relay = result.scalar_one_or_none()
    
    if not relay:
        return {"success": False, "message": "Switch not found or you are not authorized to delete it."}

    # Delete all logs associated with this relay first
    await db.execute(delete(RelayLog).where(RelayLog.relay_id == relay_id))
    
    # After the logs are gone, it is safe to delete the actual switch
    await db.execute(delete(RelayConfig).where(RelayConfig.id == relay_id))
    
    await db.commit()
    
    return {"success": True, "message": f"Switch {relay_id} deleted successfully."}