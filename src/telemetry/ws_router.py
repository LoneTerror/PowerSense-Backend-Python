import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from passlib.context import CryptContext
from pydantic import BaseModel
from typing import Dict

# Import from your existing modular structure
from src.database.client import get_db
from src.database.models import HardwareDevice, SensorData, RelayLog, User, RelayConfig
from src.auth.dependencies import get_current_token_payload

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

    def connect(self, device_id: str, websocket: WebSocket):
        self.active_connections[device_id] = websocket

    def disconnect(self, device_id: str):
        if device_id in self.active_connections:
            del self.active_connections[device_id]

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
    """Verifies the token and returns the HardwareDevice object if valid."""
    try:
        # Expected format: "Bearer NODE_01:RAW_SECRET_KEY"
        scheme, credentials = token.split(" ")
        if scheme.lower() != "bearer": return None
            
        device_id, raw_secret = credentials.split(":", 1)
        
        result = await db.execute(select(HardwareDevice).where(HardwareDevice.id == device_id))
        device = result.scalar_one_or_none()
        
        if not device or not device.is_active: return None
        if pwd_context.verify(raw_secret, device.hashed_secret): return device
            
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
    print(f"⚡ [{device.id}] Secure Hardware Connected! (Owner ID: {device.owner_id})")
    
    try:
        while True:
            payload = await websocket.receive_text()
            data = json.loads(payload)
            
            if data.get("type") == "SENSOR_DATA":
                try:
                    new_reading = SensorData(
                        owner_id=device.owner_id,
                        voltage_val=float(data.get("voltage", 0.0)),
                        current_val=float(data.get("current", 0.0)),
                        inst_power_val=float(data.get("power", 0.0)),
                        avg_current_val=float(data.get("avg_current", 0.0)),
                        avg_power_val=float(data.get("avg_power", 0.0))
                    )
                    db.add(new_reading)
                    await db.commit()
                except Exception as db_err:
                    print(f"❌ [{device.id}] Failed to save sensor data: {db_err}")
                    await db.rollback()
                    # Don't re-raise — a failed DB write should never kill the connection
                
            elif data.get("type") == "RELAY_STATUS":
                print(f"🔄 [{device.id}] Status Update -> Relay 1: {data.get('relay1')} | Relay 2: {data.get('relay2')}")
            
            elif data.get("type") == "SYNC_REQUEST":
                try:
                    # Fetch this user's actual relay rows ordered by id ascending
                    # so relay1 = lowest id, relay2 = second lowest — no hardcoding
                    relays_result = await db.execute(
                        select(RelayConfig)
                        .where(RelayConfig.owner_id == device.owner_id)
                        .order_by(RelayConfig.id.asc())
                        .limit(2)
                    )
                    relays = relays_result.scalars().all()

                    relay1_state = bool(relays[0].desired_state) if len(relays) > 0 else False
                    relay2_state = bool(relays[1].desired_state) if len(relays) > 1 else False

                    sync_payload = {
                        "type": "SYNC_RESPONSE",
                        "relay1": relay1_state,
                        "relay2": relay2_state
                    }
                    await websocket.send_json(sync_payload)
                    print(f"✅ [{device.id}] SYNC_RESPONSE sent -> R1:{relay1_state} (id:{relays[0].id if relays else 'N/A'}) | R2:{relay2_state} (id:{relays[1].id if len(relays) > 1 else 'N/A'})")

                except Exception as sync_err:
                    print(f"❌ [{device.id}] SYNC_REQUEST failed: {sync_err}")
                    await db.rollback()
                    # Send safe defaults so the ESP8266 doesn't hang waiting for a response
                    await websocket.send_json({"type": "SYNC_RESPONSE", "relay1": False, "relay2": False})
                
    except WebSocketDisconnect:
        print(f"⚠️ [{device.id}] Hardware Disconnected.")
        manager.disconnect(device.id)
    except Exception as e:
        print(f"❌ WebSocket Error: {str(e)}")
        await db.rollback()
        manager.disconnect(device.id)  # Also clean up manager on unexpected errors

# --- 5. Resolve User ID Dependency ---
async def get_current_user_id(
    token_payload: dict = Depends(get_current_token_payload), 
    db: AsyncSession = Depends(get_db)
) -> int:
    """Extracts the email from the JWT and resolves the secure User ID from the database."""
    email = token_payload.get("sub")
    query = select(User.id).where(User.email == email)
    user_id = (await db.execute(query)).scalar_one_or_none()
    
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found or deactivated.")
    return user_id


# --- 6. Android App Trigger ---
@router.post("/ws/relays/toggle")
async def toggle_relay(
    payload: RelayToggleRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    # Fetch all relays for this user ordered by id, pick by 1-based index
    relays_result = await db.execute(
        select(RelayConfig)
        .where(RelayConfig.owner_id == user_id)
        .order_by(RelayConfig.id.asc())
    )
    relays = relays_result.scalars().all()

    # payload.relay is 1 or 2 (position), map to actual DB row
    relay_index = payload.relay - 1  # Convert to 0-based index
    if relay_index < 0 or relay_index >= len(relays):
        raise HTTPException(status_code=404, detail=f"Relay {payload.relay} not found for this user.")

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