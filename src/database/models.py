from sqlalchemy import Column, Integer, Float, DateTime, String, Boolean, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.database.client import Base

# ==========================================
# 🔌 IOT & HARDWARE MODELS
# ==========================================

class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    voltage_val = Column(Float, nullable=False)
    current_val = Column(Float, nullable=False)
    inst_power_val = Column(Float, nullable=False)
    avg_current_val = Column(Float, nullable=False)
    avg_power_val = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class RelayConfig(Base):
    __tablename__ = "relay_config"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("User", backref="relays")
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

class RelayLog(Base):
    __tablename__ = "relay_log"

    id = Column(Integer, primary_key=True, index=True)
    relay_id = Column(Integer, ForeignKey("relay_config.id"), nullable=False)
    state = Column(Boolean, nullable=False)
    action_by = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


# ==========================================
# 🛡️ AUTHENTICATION & RBAC MODELS
# ==========================================

# Role Based Endpoints Assignment
class RolePolicy(Base):
    __tablename__ = "role_policies"

    # We use the role name itself as the primary key (e.g., "viewer", "operator")
    name = Column(String, primary_key=True, index=True) 
    allowed_endpoints = Column(JSON, default=list)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    
    # RBAC Core
    role = Column(String, default="viewer", nullable=False) 
    is_active = Column(Boolean, default=True)
    allowed_endpoints = Column(JSON, default=list) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action = Column(String, nullable=False) 
    ip_address = Column(String, nullable=True)
    location = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())