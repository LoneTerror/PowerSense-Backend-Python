from fastapi import WebSocket
from typing import List, Optional

class WebSocketManager:
    def __init__(self):
        self.active_clients: List[WebSocket] = []
        self.esp_socket: Optional[WebSocket] = None
        self.device_status = {
            "r1": False, 
            "r2": False, 
            "r1Start": None, 
            "r2Start": None
        }

    async def connect_client(self, websocket: WebSocket):
        await websocket.accept()
        self.active_clients.append(websocket)
        await websocket.send_json({"type": "STATUS_UPDATE", "data": self.device_status})

    async def connect_esp(self, websocket: WebSocket):
        await websocket.accept()
        self.esp_socket = websocket

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_clients:
            self.active_clients.remove(websocket)
        if websocket == self.esp_socket:
            self.esp_socket = None

    async def broadcast_status(self):
        payload = {"type": "STATUS_UPDATE", "data": self.device_status}
        for client in self.active_clients:
            if client != self.esp_socket:
                await client.send_json(payload)
                
    async def broadcast_telemetry(self, data: dict):
        payload = {"type": "SENSOR_UPDATE", "data": data}
        for client in self.active_clients:
            if client != self.esp_socket:
                await client.send_json(payload)

ws_manager = WebSocketManager()