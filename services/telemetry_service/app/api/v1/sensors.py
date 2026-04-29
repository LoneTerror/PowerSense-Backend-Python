from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from shared.powersense_db.database import get_db
from shared.powersense_db.models.sensor import SensorData

router = APIRouter()

@router.get("/latest")
async def get_latest_sensors(db: AsyncSession = Depends(get_db)):
    """Real-time metrics for Android Home Screen"""
    # Replaces the raw SELECT ... ORDER BY timestamp DESC LIMIT 1
    query = select(SensorData).order_by(desc(SensorData.timestamp)).limit(1)
    result = await db.execute(query)
    row = result.scalar_one_or_none()
    
    if not row:
        return {"voltage": 0.0, "current": 0.0, "power": 0.0, "energy": 0.0, "timestamp": ""}
        
    return {
        "voltage": row.voltage_val,
        "current": row.current_val,
        "power": row.inst_power_val,
        "energy": row.avg_power_val,
        "timestamp": row.timestamp.isoformat()
    }