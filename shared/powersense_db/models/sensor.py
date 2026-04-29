from sqlalchemy import Column, Integer, Float, DateTime
from sqlalchemy.sql import func
from shared.powersense_db.database import Base

class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    voltage_val = Column(Float, nullable=False)
    current_val = Column(Float, nullable=False)
    inst_power_val = Column(Float, nullable=False)
    avg_current_val = Column(Float, nullable=False)
    avg_power_val = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())