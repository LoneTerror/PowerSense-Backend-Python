from fastapi import APIRouter, Query, Depends, HTTPException
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Import our global auth extractors!
from src.auth.dependencies import get_current_token_payload, get_current_user_id
from src.database.client import get_db
from src.database.models import SensorData, RelayConfig
from src.telemetry.schemas import SensorDataResponse
from src.telemetry import service

router = APIRouter(
    prefix="/v1/sensors",
    tags=["Telemetry"],
    dependencies=[Depends(get_current_token_payload)]
)

@router.get("/latest", response_model=SensorDataResponse)
async def get_latest_sensors(
    user_id: int = Depends(get_current_user_id), # 🔒 Inject User ID
    db: AsyncSession = Depends(get_db)
):
    """Fetch instantaneous telemetry for Android Home Screen"""
    try:
        # Pass the user_id to the service!
        data = await service.get_latest_telemetry(user_id, db)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/history")
async def get_sensor_history(
    interval: float = Query(24.0, description="Hours to look back"),
    user_id: int = Depends(get_current_user_id), # 🔒 Inject User ID
    db: AsyncSession = Depends(get_db)
):
    time_threshold = datetime.utcnow() - timedelta(hours=interval)
    
    # 🔒 SECURE: Filter by owner_id AND time
    query = (
        select(SensorData)
        .where(
            SensorData.owner_id == user_id, 
            SensorData.timestamp >= time_threshold
        )
        .order_by(SensorData.timestamp.asc())
    )
    result = await db.execute(query)
    logs = result.scalars().all()

    if not logs:
        return {
            "current": 0.0, "avgCurrent": 0.0, "voltage": 0.0,
            "instPower": 0.0, "avgPower": 0.0, "energy_kwh": 0.0,
            "currentHistory": [], "avgCurrentHistory": [], 
            "voltageHistory": [], "powerHistory": []
        }

    avg_current = sum(log.current_val for log in logs) / len(logs)
    avg_power = sum(log.inst_power_val for log in logs) / len(logs)

    total_watt_seconds = 0.0
    for i in range(len(logs) - 1):
        t1, p1 = logs[i].timestamp, logs[i].inst_power_val
        t2, p2 = logs[i+1].timestamp, logs[i+1].inst_power_val
        time_diff = (t2 - t1).total_seconds()
        
        if 0 < time_diff < 300: 
            avg_p = (p1 + p2) / 2.0
            total_watt_seconds += avg_p * time_diff

    energy_kwh = total_watt_seconds / 3600000.0

    power_history = [{"timestamp": log.timestamp.isoformat() + "Z", "value": log.inst_power_val} for log in logs]
    current_history = [{"timestamp": log.timestamp.isoformat() + "Z", "value": log.current_val} for log in logs]
    voltage_history = [{"timestamp": log.timestamp.isoformat() + "Z", "value": log.voltage_val} for log in logs]

    return {
        "current": logs[-1].current_val,
        "avgCurrent": round(avg_current, 2),
        "voltage": logs[-1].voltage_val,
        "instPower": logs[-1].inst_power_val,
        "avgPower": round(avg_power, 2),
        "energy_kwh": round(energy_kwh, 6),
        "currentHistory": current_history,
        "avgCurrentHistory": current_history,
        "voltageHistory": voltage_history,
        "powerHistory": power_history
    }

@router.get("/relay-usage")
async def get_relay_usage(
    interval: float = Query(24.0),
    user_id: int = Depends(get_current_user_id), # 🔒 Inject User ID
    db: AsyncSession = Depends(get_db)
):
    """Dynamically fetches the relays owned by THIS user."""
    # 🔒 SECURE: Fetch only the relays this user owns to populate the Android UI
    query = select(RelayConfig).where(RelayConfig.owner_id == user_id)
    result = await db.execute(query)
    user_relays = result.scalars().all()
    
    usage_data = {}
    for i, relay in enumerate(user_relays):
        # We will dynamically generate the JSON keys Android expects (relay1, relay2)
        # In the future, you will map this to the RelayLog table for actual time calculation!
        usage_data[f"relay{i+1}"] = 0.0  
        
    # Fallbacks so Ktor doesn't crash if the user has no relays yet
    if "relay1" not in usage_data: usage_data["relay1"] = 0.0
    if "relay2" not in usage_data: usage_data["relay2"] = 0.0

    return usage_data