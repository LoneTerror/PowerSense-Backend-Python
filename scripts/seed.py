import asyncio
import random
import os
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# 1. Load the .env file BEFORE importing the database client
load_dotenv()

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from src.database.client import AsyncSessionLocal
from src.database.models import SensorData, RelayConfig, RelayLog

async def seed_database():
    print("🌱 Starting Database Seeding...")
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. Seed Relay Configurations (Upsert to avoid duplicates)
            print("⚙️ Seeding Relay Configurations...")
            for relay_id, name, desc in [(1, 'Relay 1', 'Main Output'), (2, 'Relay 2', 'Secondary Output')]:
                existing = await db.get(RelayConfig, relay_id)
                if not existing:
                    db.add(RelayConfig(id=relay_id, name=name, description=desc))
            
            # 2. Seed Sensor Data
            print("📊 Generating 96 historical sensor entries...")
            now = datetime.now(timezone.utc)
            
            # Create 24 hours of data (1 reading every 15 mins)
            for i in range(96):
                timestamp = now - timedelta(minutes=15 * i)
                voltage = round(random.uniform(225.0, 235.0), 2)
                power = round(random.uniform(50.0, 2000.0), 2)
                current = round(power / voltage, 2)
                
                sensor_entry = SensorData(
                    voltage_val=voltage,
                    current_val=current,
                    inst_power_val=power,
                    avg_current_val=current,
                    avg_power_val=power,
                    timestamp=timestamp
                )
                db.add(sensor_entry)

            # 3. Seed Relay Logs
            print("🔌 Seeding Relay Logs...")
            log1 = RelayLog(relay_id=1, state=True, action_by="Seed Script", timestamp=now - timedelta(hours=5))
            log2 = RelayLog(relay_id=1, state=False, action_by="Seed Script", timestamp=now - timedelta(hours=1))
            db.add_all([log1, log2])

            # Commit all changes to PostgreSQL
            await db.commit()
            print("✅ Seeding complete!")

        except Exception as e:
            await db.rollback()
            print(f"❌ Seeding failed: {str(e)}")

if __name__ == "__main__":
    # Windows-specific fix for asyncio loops (Required for asyncpg on Windows)
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(seed_database())