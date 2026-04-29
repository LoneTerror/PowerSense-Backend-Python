from pydantic import BaseModel, Field

class SensorDataIngest(BaseModel):
    voltage: float
    current: float
    power: float = Field(..., lt=6000, description="Ignored unrealistic power reading")
    avg_current: float
    avg_power: float