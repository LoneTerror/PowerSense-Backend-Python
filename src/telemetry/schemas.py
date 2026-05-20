from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class SensorDataCreate(BaseModel):
    voltage: float
    current: float
    power: float = Field(..., lt=6000)
    avg_current: float
    avg_power: float

class SensorDataResponse(BaseModel):
    voltage: float
    current: float
    power: float
    energy: float
    timestamp: datetime

    class Config:
        from_attributes = True