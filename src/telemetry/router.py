import secrets
from passlib.context import CryptContext
from fastapi import APIRouter, Query, Depends, HTTPException
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Import our global auth extractors!
from src.auth.dependencies import get_current_token_payload, get_current_user_id
from src.database.client import get_db
from src.database.models import SensorData, RelayConfig, HardwareDevice
from src.telemetry.schemas import SensorDataResponse
from src.telemetry import service

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
    """Calculates true appliance ON-time based on RelayLog time deltas."""
    # 🚀 Outsource the heavy time-delta calculation to the service layer!
    usage_data = await service.calculate_relay_usage(user_id, interval, db)
    
    return usage_data

@router.post("/provision-hardware")
async def provision_new_device(
    user_id: int = Depends(get_current_user_id), # 🔒 Automatically links hardware to logged-in user
    db: AsyncSession = Depends(get_db)
):
    """Generates a permanent API key for a new ESP8266 unit."""
    raw_token = secrets.token_hex(32) 
    device_id = f"NODE_{secrets.token_hex(4).upper()}"
    
    hashed_token = pwd_context.hash(raw_token)
    
    new_device = HardwareDevice(
        id=device_id, 
        owner_id=user_id, 
        hashed_secret=hashed_token
    )
    db.add(new_device)
    await db.commit()
    
    # ⚠️ Return the string exactly as the ESP8266 needs it
    return {
        "device_id": device_id,
        "esp8266_hardware_token": f"{device_id}:{raw_token}",
        "message": "Copy this token to your ESP8266 code. The backend only saves the hash!"
    }