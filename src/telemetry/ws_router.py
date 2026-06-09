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
        self.online_status: Dict[str, bool] = {}       # device_id -> is_online
        self.pending_pings: Dict[str, int] = {}        # device_id -> unanswered ping count
        self.last_pong: Dict[str, float] = {}          # device_id -> timestamp of last pong

    def connect(self, device_id: str, websocket: WebSocket):
        self.active_connections[device_id] = websocket
        self.online_status[device_id] = True
        self.pending_pings[device_id] = 0
        self.last_pong[device_id] = asyncio.get_event_loop().time()

    def disconnect(self, device_id: str):
        self.active_connections.pop(device_id, None)
        self.online_status[device_id] = False
        self.pending_pings.pop(device_id, None)
        self.last_pong.pop(device_id, None)

    def record_pong(self, device_id: str):
        """Call this whenever ANY message arrives — data counts as proof of life."""
        self.pending_pings[device_id] = 0
        self.last_pong[device_id] = asyncio.get_event_loop().time()
        self.online_status[device_id] = True

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

# --- 3. Hardware Database Verification ---
async def verify_hardware(token: str, db: AsyncSession):
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

# --- 4. Ping Loop ---
async def ping_loop(device_id: str, websocket: WebSocket):
    """
    Runs as a parallel task alongside the receive loop.
    Sends a PING every 10 seconds.
    If 3 consecutive pings go unanswered, closes the WebSocket.
    Any incoming message (SENSOR_DATA, PONG, anything) resets the counter.
    """
    PING_INTERVAL  = 10   # seconds between pings
    MAX_MISSED     = 3    # consecutive unanswered pings before declaring offline

    print(f"🏓 [{device_id}] Ping loop started. Interval:{PING_INTERVAL}s Max missed:{MAX_MISSED}")

    try:
        while True:
            await asyncio.sleep(PING_INTERVAL)

            # Check if device is still in the manager (may have already disconnected)
            if device_id not in manager.active_connections:
                print(f"🏓 [{device_id}] Ping loop exiting — device no longer registered.")
                break

            # Increment unanswered ping count
            manager.pending_pings[device_id] = manager.pending_pings.get(device_id, 0) + 1
            missed = manager.pending_pings[device_id]

            print(f"🏓 [{device_id}] Sending PING (missed so far: {missed}/{MAX_MISSED})")

            # Send PING as a JSON message — ESP8266 must respond with PONG
            try:
                await websocket.send_json({"type": "PING"})
            except Exception as send_err:
                print(f"🏓 [{device_id}] PING send failed: {send_err} — forcing disconnect.")
                await websocket.close(code=status.WS_1001_GOING_AWAY)
                break

            # If 3 pings have gone unanswered, declare offline and close
            if missed >= MAX_MISSED:
                print(f"💀 [{device_id}] {MAX_MISSED} pings unanswered — device considered OFFLINE.")
                manager.online_status[device_id] = False

                # Update DB status with a fresh session
                async with AsyncSessionLocal() as fresh_db:
                    try:
                        fresh_device = (await fresh_db.execute(
                            select(HardwareDevice).where(HardwareDevice.id == device_id)
                        )).scalar_one_or_none()
                        if fresh_device:
                            fresh_device.is_online = False
                            fresh_device.last_seen = datetime.now(timezone.utc)
                            await fresh_db.commit()
                            print(f"📴 [{device_id}] Marked OFFLINE in DB after ping timeout.")
                    except Exception as db_err:
                        print(f"⚠️ [{device_id}] Failed to mark offline: {db_err}")
                        await fresh_db.rollback()

                # Force close the WebSocket — triggers WebSocketDisconnect in receive loop
                try:
                    await websocket.close(code=status.WS_1001_GOING_AWAY)
                except Exception:
                    pass
                break

    except asyncio.CancelledError:
        # Normal — task is cancelled when the receive loop exits
        print(f"🏓 [{device_id}] Ping loop cancelled cleanly.")

# --- 5. Hardware WebSocket Gateway ---
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

    # Mark online in DB
    try:
        device.is_online = True
        device.last_seen = datetime.now(timezone.utc)
        await db.commit()
        print(f"⚡ [{device.id}] Online. (Owner ID: {device.owner_id})")
    except Exception as e:
        print(f"⚠️ [{device.id}] Failed to mark online: {e}")
        await db.rollback()

    # Start ping loop as a parallel background task
    ping_task = asyncio.create_task(ping_loop(device.id, websocket))

    try:
        while True:
            try:
                payload = await websocket.receive_text()
            except Exception as recv_err:
                print(f"💀 [{device.id}] receive_text() FAILED: {type(recv_err).__name__}: {recv_err}")
                raise

            # ANY incoming message = device is alive, reset ping counter
            manager.record_pong(device.id)

            try:
                data = json.loads(payload)
            except json.JSONDecodeError as je:
                print(f"⚠️ [{device.id}] Invalid JSON: {payload[:100]} | {je}")
                continue

            msg_type = data.get("type")

            if msg_type == "SENSOR_DATA":
                try:
                    print(f"📡 [{device.id}] SENSOR_DATA -> V:{data.get('voltage')} I:{data.get('current')} P:{data.get('power')}")
                    new_reading = SensorData(
                        owner_id=device.owner_id,
                        voltage_val=float(data.get("voltage", 0.0)),
                        current_val=float(data.get("current", 0.0)),
                        inst_power_val=float(data.get("power", 0.0)),
                        avg_current_val=float(data.get("avg_current", 0.0)),
                        avg_power_val=float(data.get("avg_power", 0.0))
                    )
                    db.add(new_reading)
                    device.last_seen = datetime.now(timezone.utc)
                    await db.commit()
                except Exception as db_err:
                    print(f"❌ [{device.id}] Failed to save sensor data: {db_err}")
                    await db.rollback()

            elif msg_type == "PONG":
                # Explicit PONG response from ESP8266
                print(f"🏓 [{device.id}] PONG received.")
                # record_pong() already called above for ALL messages

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
                    await websocket.send_json({"type": "SYNC_RESPONSE", "relay1": False, "relay2": False})

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
        # Cancel the ping loop task
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass

        # Update registry and DB — relays NOT touched
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


# --- 6. Device Status Endpoint ---
@router.get("/ws/device/status/{device_id}")
async def get_device_status(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    result = await db.execute(
        select(HardwareDevice).where(
            HardwareDevice.id == device_id,
            HardwareDevice.owner_id == user_id
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")

    # Cross-check DB status with live connection manager
    # DB alone can be stale if server restarted — manager is always live
    is_online = manager.is_online(device_id) and device.is_online

    seconds_since_seen = None
    if device.last_seen:
        seconds_since_seen = int((datetime.now(timezone.utc) - device.last_seen).total_seconds())

    return {
        "device_id": device.id,
        "is_online": is_online,
        "last_seen": device.last_seen,
        "seconds_since_seen": seconds_since_seen,
        "pending_pings": manager.pending_pings.get(device_id, 0)
    }


# --- 7. Android App Relay Toggle ---
@router.post("/ws/relays/toggle")
async def toggle_relay(
    payload: RelayToggleRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    relays_result = await db.execute(
        select(RelayConfig)
        .where(RelayConfig.owner_id == user_id)
        .order_by(RelayConfig.id.asc())
    )
    relays = relays_result.scalars().all()

    relay_index = payload.relay - 1
    if relay_index < 0 or relay_index >= len(relays):
        raise HTTPException(status_code=404, detail=f"Relay {payload.relay} not found.")

    relay = relays[relay_index]
    relay.desired_state = payload.state
    await db.commit()

    hardware_command = {"type": "COMMAND", "relay": payload.relay, "state": payload.state}
    success = await manager.send_command(payload.device_id, hardware_command)

    try:
        action_log = RelayLog(relay_id=relay.id, state=payload.state, action_by=f"User {user_id}")
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