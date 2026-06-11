from pydantic import BaseModel
from typing import Optional

class RelayConfigUpdate(BaseModel):
    name: str
    description: Optional[str] = None
    device_id: str               
    physical_pin: int            
    threshold: Optional[float] = None
    threshold_unit: str = "A"

class RelayToggle(BaseModel):
    state: bool

class RelayConfigResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    desired_state: bool
    device_id: str               
    physical_pin: int            
    threshold: Optional[float] = None
    threshold_unit: str = "A"

    class Config:
        from_attributes = True