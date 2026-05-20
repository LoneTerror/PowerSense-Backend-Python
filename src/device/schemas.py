from pydantic import BaseModel
from typing import Optional

class RelayConfigUpdate(BaseModel):
    name: str
    description: Optional[str] = None

class RelayToggle(BaseModel):
    state: bool

class RelayConfigResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True