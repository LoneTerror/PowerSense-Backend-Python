from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import delete
from src.database.models import RelayConfig, RelayLog
from src.device.schemas import RelayConfigUpdate

async def get_all_configs(user_id: int, db: AsyncSession):
    # 🔒 SECURE: Filters the database so the user only sees THEIR devices
    query = select(RelayConfig).where(RelayConfig.owner_id == user_id).order_by(RelayConfig.id.asc())
    result = await db.execute(query)
    return result.scalars().all()

async def update_config(relay_id: int, user_id: int, payload: RelayConfigUpdate, db: AsyncSession):
    # 🔒 SECURE: Ensures the user actually owns the relay before allowing an update
    query = select(RelayConfig).where(RelayConfig.id == relay_id, RelayConfig.owner_id == user_id)
    result = await db.execute(query)
    relay = result.scalar_one_or_none()
    
    if relay:
        relay.name = payload.name
        relay.description = payload.description
    else:
        # If the relay doesn't exist yet, create it and assign it to this specific user!
        new_relay = RelayConfig(
            id=relay_id, 
            owner_id=user_id, 
            name=payload.name, 
            description=payload.description
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
    # 🔒 SECURE: Only deletes if the relay ID exists AND the owner ID matches the logged-in user (idempotent check)
    stmt = delete(RelayConfig).where(RelayConfig.id == relay_id, RelayConfig.owner_id == user_id)
    
    result = await db.execute(stmt)
    
    if result.rowcount == 0:
        return {"success": False, "message": "Switch not found or you are not authorized to delete it."}
        
    await db.commit()
    return {"success": True, "message": f"Switch {relay_id} deleted successfully."}