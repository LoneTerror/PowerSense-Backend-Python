from pydantic import BaseModel

class UserUpdate(BaseModel):
    full_name: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# Admin Management
class AdminUserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "viewer"
    allowed_endpoints: list[str] = []

class AdminUserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    allowed_endpoints: list[str] | None = None

class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    allowed_endpoints: list[str]
    
    class Config:
        from_attributes = True

# RBAC Role Structure via API
class RolePolicyCreate(BaseModel):
    name: str
    allowed_endpoints: list[str] = []

class RolePolicyUpdate(BaseModel):
    allowed_endpoints: list[str]
    
class RolePolicyResponse(BaseModel):
    name: str
    allowed_endpoints: list[str]
    
    class Config:
        from_attributes = True