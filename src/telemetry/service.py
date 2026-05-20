from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from src.database.models import SensorData
from src.telemetry.schemas import SensorDataCreate

async def get_latest_telemetry(db: AsyncSession) -> dict:
    """Fetches the most recent sensor reading from the database."""
    query = select(SensorData).order_by(desc(SensorData.timestamp)).limit(1)
    result = await db.execute(query)
    row = result.scalar_one_or_none()
    
    if not row:
        return {"voltage": 0.0, "current": 0.0, "power": 0.0, "energy": 0.0, "timestamp": None}
        
    return {
        "voltage": row.voltage_val,
        "current": row.current_val,
        "power": row.inst_power_val,
        "energy": row.avg_power_val,
        "timestamp": row.timestamp
    }

async def save_telemetry(data: SensorDataCreate, db: AsyncSession):
    """Persists validated hardware data to the database."""
    new_record = SensorData(
        voltage_val=data.voltage,
        current_val=data.current,
        inst_power_val=data.power,
        avg_current_val=data.avg_current,
        avg_power_val=data.avg_power
    )
    db.add(new_record)
    await db.commit()
    return new_record