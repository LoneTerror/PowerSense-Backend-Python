# Add these lines near the top of env.py
from shared.powersense_db.database import Base
from shared.powersense_db.models.sensor import SensorData
from shared.powersense_db.models.relay import RelayConfig, RelayLog

target_metadata = Base.metadata