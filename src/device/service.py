from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.models import RelayConfig, RelayLog
from src.device.schemas import RelayConfigUpdate

async def get_all_configs(db: AsyncSession):
    query = select(RelayConfig).order_by(RelayConfig.id.asc())
    result = await db.execute(query)
    return result.scalars().all()

async def update_config(relay_id: int, payload: RelayConfigUpdate, db: AsyncSession):
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

async def log_relay_toggle(relay_id: int, state: bool, db: AsyncSession):
    action_log = RelayLog(
        relay_id=relay_id,
        state=state,
        action_by="App/Web"
    )
    db.add(action_log)
    await db.commit()