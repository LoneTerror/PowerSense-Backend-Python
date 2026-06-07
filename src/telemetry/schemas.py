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



class TariffUpdate(BaseModel):
    rate_per_kwh: float
    currency: str = "INR"

class TargetUpdate(BaseModel):
    target_monthly_kwh: float
    target_monthly_cost: float