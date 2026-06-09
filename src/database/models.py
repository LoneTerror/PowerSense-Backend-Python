from sqlalchemy import Column, Integer, Float, DateTime, String, Boolean, ForeignKey, JSON, Date, UniqueConstraint
from datetime import datetime, timezone
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.database.client import Base

# ==========================================
# 🔌 IOT & HARDWARE MODELS
# ==========================================

class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
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
    desired_state = Column(Boolean, default=False)

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

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    is_read = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class TariffPlan(Base):
    """Stores electricity pricing to calculate cost targets."""
    __tablename__ = "tariff_plans"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    rate_per_kwh = Column(Float, nullable=False, default=8.0) # e.g., 8.0 INR per kWh
    currency = Column(String, default="INR")
    effective_from = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class DailyEnergySummary(Base):
    """Pre-calculated daily stats. Prevents scanning millions of raw sensor rows."""
    __tablename__ = "daily_energy_summary"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    summary_date = Column(Date, nullable=False)
    
    total_kwh = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    peak_power_w = Column(Float, default=0.0)
    avg_power_w = Column(Float, default=0.0)
    
    # Ensures we only have one summary row per user per day
    __table_args__ = (UniqueConstraint('owner_id', 'summary_date', name='uix_user_daily_date'),)

class MonthlyEnergySummary(Base):
    """Monthly rollup. Used as the Ground Truth 'Label' for training the ML model."""
    __tablename__ = "monthly_energy_summary"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    month = Column(Integer, nullable=False) # 1 - 12
    year = Column(Integer, nullable=False)  # e.g., 2026
    
    total_kwh = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    peak_power_w = Column(Float, default=0.0)
    
    __table_args__ = (UniqueConstraint('owner_id', 'month', 'year', name='uix_user_monthly'),)

class ConsumptionTarget(Base):
    """User's budget and limits for generating ML reduction digests."""
    __tablename__ = "consumption_targets"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    
    target_monthly_kwh = Column(Float, nullable=False)
    target_monthly_cost = Column(Float, nullable=False)
    
    valid_for_month = Column(Integer, nullable=False)
    valid_for_year = Column(Integer, nullable=False)
    
    __table_args__ = (UniqueConstraint('owner_id', 'valid_for_month', 'valid_for_year', name='uix_user_target'),)

class MLPrediction(Base):
    """Stores daily ML outputs to track drift and show users their forecasting."""
    __tablename__ = "ml_predictions"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    predicted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    predicted_cost_eod = Column(Float, nullable=False) # End of Day
    predicted_cost_eom = Column(Float, nullable=False) # End of Month
    
    # The crucial metric for the Android UI: "You need to reduce usage by X kWh/day"
    required_daily_reduction_kwh = Column(Float, default=0.0) 
    
    model_version = Column(String, default="xgboost-v1.0")

class HardwareDevice(Base):
    __tablename__ = "hardware_devices"

    id = Column(String, primary_key=True, index=True) # e.g., "NODE_A1B2C3"
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    hashed_secret = Column(String, nullable=False)    # Bcrypt hash of the hardware token
    is_active = Column(Boolean, default=True)         # Master kill-switch
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_online = Column(Boolean, default=False, nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=True)