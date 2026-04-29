from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from shared.powersense_db.database import Base

class RelayConfig(Base):
    __tablename__ = "relay_config"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

class RelayLog(Base):
    __tablename__ = "relay_log"

    id = Column(Integer, primary_key=True, index=True)
    relay_id = Column(Integer, ForeignKey("relay_config.id"), nullable=False)
    state = Column(Boolean, nullable=False) # 1 or 0 mapped to Boolean
    action_by = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())