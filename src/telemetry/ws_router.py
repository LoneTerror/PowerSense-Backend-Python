import json
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from passlib.context import CryptContext
from pydantic import BaseModel
from typing import Dict

from src.database.client import get_db, AsyncSessionLocal
from src.database.models import HardwareDevice, SensorData, RelayLog, User, RelayConfig
from src.auth.dependencies import get_current_token_payload, get_current_user_id

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter()

# --- 1. Schemas ---
class RelayToggleRequest(BaseModel):
    device_id: str
    relay: int
    state: bool

# --- 2. Connection Manager ---
class DeviceConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.online_status: Dict[str, bool] = {}
        # Tracks if the device was previously drawing power
        self.was_drawing_power: Dict[str, bool] = {}

    def connect(self, device_id: str, websocket: WebSocket):
        self.active_connections[device_id] = websocket
        self.online_status[device_id] = True

    def disconnect(self, device_id: str):
        self.active_connections.pop(device_id, None)
        self.online_status[device_id] = False

    def is_online(self, device_id: str) -> bool:
        return self.online_status.get(device_id, False)

    async def send_command(self, device_id: str, command: dict) -> bool:
        websocket = self.active_connections.get(device_id)
        if websocket:
            try:
                await websocket.send_json(command)
                return True
            except Exception:
                return False
        return False

manager = DeviceConnectionManager()

# --- 3. Hardware Token Verification ---
async def verify_hardware(token: str, db: AsyncSession):
    """Verifies the Bearer token and returns the HardwareDevice if valid."""
    try:
        scheme, credentials = token.split(" ")
        if scheme.lower() != "bearer":
            return None
        device_id, raw_secret = credentials.split(":", 1)

        result = await db.execute(select(HardwareDevice).where(HardwareDevice.id == device_id))
        device = result.scalar_one_or_none()

        if not device or not device.is_active:
            return None
        if pwd_context.verify(raw_secret, device.hashed_secret):
            return device

    except ValueError:
        pass
    return None

# --- 4. Hardware WebSocket Gateway ---
@router.websocket("/ws/device")
async def hardware_gateway(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    auth_header = websocket.headers.get("authorization")

    if not auth_header:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    device = await verify_hardware(auth_header, db)
    if not device:
        print("⛔ Unauthorized ESP8266 connection attempt blocked.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    manager.connect(device.id, websocket)

    # Mark device online in DB
    try:
        device.is_online = True
        device.last_seen = datetime.now(timezone.utc)
        await db.commit()
        print(f"⚡ [{device.id}] Online. (Owner ID: {device.owner_id})")
    except Exception as e:
        print(f"⚠️ [{device.id}] Failed to mark online: {e}")
        await db.rollback()

    try:
        while True:
            try:
                payload = await websocket.receive_text()
            except Exception as recv_err:
                print(f"💀 [{device.id}] receive_text() FAILED: {type(recv_err).__name__}: {recv_err}")
                raise

            try:
                data = json.loads(payload)
            except json.JSONDecodeError as je:
                print(f"⚠️ [{device.id}] Invalid JSON: {payload[:100]} | {je}")
                continue

            msg_type = data.get("type")

            if msg_type == "SENSOR_DATA":
                try:
                    # 1. Extract values
                    voltage = float(data.get("voltage", 0.0))
                    current = float(data.get("current", 0.0))
                    power = float(data.get("power", 0.0))
                    avg_current = float(data.get("avg_current", 0.0))
                    avg_power = float(data.get("avg_power", 0.0))

                    # 2. Determine Current State
                    # Consider anything under 0.5 Watts as "Zero" to account for tiny fluctuations
                    is_drawing_power = power > 0.5 
                    was_drawing_power = manager.was_drawing_power.get(device.id, True)

                    # 3. The Filtering Logic
                    should_save = False

                    if is_drawing_power:
                        # Rule A: Always save if it's actively consuming power
                        should_save = True
                    elif was_drawing_power and not is_drawing_power:
                        # Rule B: Save exactly ONE zero-reading when it turns off
                        should_save = True
                    else:
                        # Rule C: Ignore continuous zero readings
                        should_save = False

                    # 4. Save to DB if required
                    if should_save:
                        new_reading = SensorData(
                            owner_id=device.owner_id,
                            voltage_val=voltage,
                            current_val=current,
                            inst_power_val=power,
                            avg_current_val=avg_current,
                            avg_power_val=avg_power
                        )
                        db.add(new_reading)
                        
                    # 5. ALWAYS update the 'last_seen' timestamp, even if we drop the DB write
                    # This proves the device is online, even if it's using 0W
                    device.last_seen = datetime.now(timezone.utc)
                    await db.commit()

                    # 6. Update the state tracker
                    manager.was_drawing_power[device.id] = is_drawing_power

                except Exception as db_err:
                    print(f"❌ [{device.id}] Failed to process sensor data: {db_err}")
                    await db.rollback()

            elif msg_type == "RELAY_STATUS":
                print(f"🔄 [{device.id}] Relay Status -> R1:{data.get('relay1')} | R2:{data.get('relay2')}")

            elif msg_type == "SYNC_REQUEST":
                try:
                    relays_result = await db.execute(
                        select(RelayConfig)
                        .where(RelayConfig.owner_id == device.owner_id)
                        .order_by(RelayConfig.id.asc())
                        .limit(2)
                    )
                    relays = relays_result.scalars().all()

                    relay1_state = bool(relays[0].desired_state) if len(relays) > 0 else False
                    relay2_state = bool(relays[1].desired_state) if len(relays) > 1 else False

                    await websocket.send_json({
                        "type": "SYNC_RESPONSE",
                        "relay1": relay1_state,
                        "relay2": relay2_state
                    })
                    print(f"✅ [{device.id}] SYNC_RESPONSE -> R1:{relay1_state} | R2:{relay2_state}")

                except Exception as sync_err:
                    print(f"❌ [{device.id}] SYNC failed: {sync_err}")
                    await db.rollback()
                    await websocket.send_json({
                        "type": "SYNC_RESPONSE",
                        "relay1": False,
                        "relay2": False
                    })

            else:
                print(f"⚠️ [{device.id}] Unknown message type: {msg_type}")

    except WebSocketDisconnect as wd:
        print(f"⚠️ [{device.id}] Disconnected. Code:{wd.code} — Relays holding last state.")

    except Exception as e:
        import traceback
        print(f"❌ [{device.id}] FATAL Error: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        await db.rollback()

    finally:
        # Always runs — whether clean disconnect, heartbeat timeout, or crash
        # Relays are NOT touched — physical hardware holds last state
        manager.disconnect(device.id)

        async with AsyncSessionLocal() as fresh_db:
            try:
                fresh_device = (await fresh_db.execute(
                    select(HardwareDevice).where(HardwareDevice.id == device.id)
                )).scalar_one_or_none()
                if fresh_device:
                    fresh_device.is_online = False
                    fresh_device.last_seen = datetime.now(timezone.utc)
                    await fresh_db.commit()
                    print(f"📴 [{device.id}] Marked OFFLINE in DB.")
            except Exception as db_err:
                print(f"⚠️ [{device.id}] Failed to mark offline: {db_err}")
                await fresh_db.rollback()


# --- 5. Device Status Endpoint ---
@router.get("/ws/device/status/{device_id}")
async def get_device_status(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Returns live connection status and last seen timestamp for a device."""
    result = await db.execute(
        select(HardwareDevice).where(
            HardwareDevice.id == device_id,
            HardwareDevice.owner_id == user_id
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")

    # Cross-check DB with live manager — DB can be stale if server restarted
    is_online = manager.is_online(device_id) and device.is_online

    seconds_since_seen = None
    if device.last_seen:
        seconds_since_seen = int(
            (datetime.now(timezone.utc) - device.last_seen).total_seconds()
        )

    return {
        "device_id": device.id,
        "is_online": is_online,
        "last_seen": device.last_seen,
        "seconds_since_seen": seconds_since_seen
    }


# --- 6. Android App Relay Toggle ---
@router.post("/ws/relays/toggle")
async def toggle_relay(
    payload: RelayToggleRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Toggles a relay state — updates DB and dispatches command to hardware."""
    relays_result = await db.execute(
        select(RelayConfig)
        .where(RelayConfig.owner_id == user_id)
        .where(RelayConfig.device_id == payload.device_id)
        .order_by(RelayConfig.id.asc())
    )
    relays = relays_result.scalars().all()

    relay_index = payload.relay - 1
    if relay_index < 0 or relay_index >= len(relays):
        raise HTTPException(status_code=404, detail="Relay not found on this device.")

    relay = relays[relay_index]
    relay.desired_state = payload.state
    await db.commit()

    hardware_command = {
        "type": "COMMAND",
        "relay": payload.relay,
        "state": payload.state
    }
    success = await manager.send_command(payload.device_id, hardware_command)

    try:
        action_log = RelayLog(
            relay_id=relay.id,
            state=payload.state,
            action_by=f"User {user_id}"
        )
        db.add(action_log)
        await db.commit()
    except Exception as e:
        print(f"⚠️ Audit log failed: {e}")

    return {
        "status": "success",
        "queued": not success,
        "relay_db_id": relay.id,
        "message": "Command dispatched or queued for sync."
    }