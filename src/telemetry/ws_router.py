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
                # Save to PostgreSQL matching your exact SensorData model
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
                
            elif data.get("type") == "RELAY_STATUS":
                print(f"🔄 [{device.id}] Status Update -> Relay 1: {data.get('relay1')} | Relay 2: {data.get('relay2')}")
            
            elif data.get("type") == "SYNC_REQUEST":
                # Look up the current desired states for this device
                # (Simplified lookup example - adjust based on your table relations)
                r1 = await db.execute(select(RelayConfig.desired_state).where(RelayConfig.id == 1))
                r2 = await db.execute(select(RelayConfig.desired_state).where(RelayConfig.id == 2))
    
                sync_payload = {
                    "type": "SYNC_RESPONSE",
                    "relay1": r1.scalar() or False,
                    "relay2": r2.scalar() or False
                }
                await websocket.send_json(sync_payload)
                
    except WebSocketDisconnect:
        print(f"⚠️ [{device.id}] Hardware Disconnected.")
        manager.disconnect(device.id)
    except Exception as e:
        print(f"❌ WebSocket Error: {str(e)}")
        await db.rollback()

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
    # 1. Update the 'Desired State' in DB first
    # Assuming RelayConfig.id matches the payload.relay ID
    result = await db.execute(select(RelayConfig).where(RelayConfig.id == payload.relay))
    relay = result.scalar_one_or_none()
    
    if relay:
        relay.desired_state = payload.state # Ensure this column exists in RelayConfig
        await db.commit()

    # 2. Dispatch command
    hardware_command = {"type": "COMMAND", "relay": payload.relay, "state": payload.state}
    success = await manager.send_command(payload.device_id, hardware_command)
    
    # 3. Log state change (Audit Trail)
    try:
        action_log = RelayLog(relay_id=payload.relay, state=payload.state, action_by=f"User {user_id}")
        db.add(action_log)
        await db.commit()
    except Exception as e:
        print(f"⚠️ Audit log failed: {e}")
        
    # 4. Return success even if offline (Queued)
    return {
        "status": "success", 
        "queued": not success, 
        "message": "Command dispatched or queued for sync."
    }