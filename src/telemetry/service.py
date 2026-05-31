from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc, desc
from src.database.models import SensorData, RelayLog, RelayConfig
from src.telemetry.schemas import SensorDataCreate

async def get_latest_telemetry(user_id: int, db: AsyncSession) -> dict:
    """Fetches the most recent sensor reading ONLY for this specific user."""
    
    # 🔒 SECURE: Added SensorData.owner_id == user_id
    query = (
        select(SensorData)
        .where(SensorData.owner_id == user_id)
        .order_by(desc(SensorData.timestamp))
        .limit(1)
    )
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

async def save_telemetry(user_id: int, data: SensorDataCreate, db: AsyncSession):
    """Persists validated hardware data to the database."""
    new_record = SensorData(
        owner_id=user_id,
        voltage_val=data.voltage,
        current_val=data.current,
        inst_power_val=data.power,
        avg_current_val=data.avg_current,
        avg_power_val=data.avg_power
    )
    db.add(new_record)
    await db.commit()
    return new_record

async def calculate_relay_usage(user_id: int, interval_hours: int, db: AsyncSession) -> dict:
    """Calculates true appliance ON-time based on RelayLog time deltas."""
    
    # Using datetime.now(timezone.utc) instead of datetime.utcnow()
    now = datetime.now(timezone.utc)
    start_time_window = now - timedelta(hours=interval_hours)

    # Fetch the user's real devices
    relays_query = select(RelayConfig).where(RelayConfig.owner_id == user_id).order_by(RelayConfig.id)
    user_relays = (await db.execute(relays_query)).scalars().all()

    usage_data = {}

    for i, relay in enumerate(user_relays):
        # Get the last known state BEFORE the time window
        last_state_query = (
            select(RelayLog)
            .where(RelayLog.relay_id == relay.id)
            .where(RelayLog.timestamp < start_time_window)
            .order_by(RelayLog.timestamp.desc())
            .limit(1)
        )
        last_state_log = (await db.execute(last_state_query)).scalar_one_or_none()
        
        is_on = last_state_log.state if last_state_log else False
        current_on_time = start_time_window if is_on else None
        total_seconds = 0.0

        # Fetch all toggle events INSIDE the time window
        logs_query = (
            select(RelayLog)
            .where(RelayLog.relay_id == relay.id)
            .where(RelayLog.timestamp >= start_time_window)
            .order_by(asc(RelayLog.timestamp))
        )
        logs_in_window = (await db.execute(logs_query)).scalars().all()

        # Calculate exact time deltas
        for log in logs_in_window:
            if log.state == True and not is_on:
                # Appliance turned ON
                is_on = True
                current_on_time = log.timestamp
            elif log.state == False and is_on:
                # Appliance turned OFF, calculate duration
                is_on = False
                if current_on_time:
                    total_seconds += (log.timestamp - current_on_time).total_seconds()
                    current_on_time = None

        # If it is STILL running right now, calculate time up to this exact second
        if is_on and current_on_time:
            total_seconds += (now - current_on_time).total_seconds()

        # Convert to hours and map to frontend JSON keys (relay1Hours, relay2Hours)
        hours_on = total_seconds / 3600.0
        usage_data[f"relay{i+1}Hours"] = round(hours_on, 2)

    # Fill remaining slots with 0.0 if user has fewer than 2 relays, so Android doesn't crash
    if "relay1Hours" not in usage_data: usage_data["relay1Hours"] = 0.0
    if "relay2Hours" not in usage_data: usage_data["relay2Hours"] = 0.0

    return usage_data