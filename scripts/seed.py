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
from src.database.models import SensorData, RelayConfig, RelayLog, User, RolePolicy
from src.common.security import get_password_hash

async def seed_database():
    print("🌱 Starting Enterprise Database Seeding...")
    
    async with AsyncSessionLocal() as db:
        try:
            # ==========================================
            # 1. SEED ROLE POLICIES
            # ==========================================
            print("📜 Injecting Role Policies...")
            roles = ["admin", "consumer", "viewer"]
            for role_name in roles:
                existing_role = await db.get(RolePolicy, role_name)
                if not existing_role:
                    db.add(RolePolicy(name=role_name, allowed_endpoints=["*"]))
            await db.commit()

            # ==========================================
            # 2. SEED MASTER ADMIN USER
            # ==========================================
            print("👤 Fetching/Creating Master Admin User...")
            master_email = "chakrabortyprasun10@gmail.com"
            
            result = await db.execute(select(User).where(User.email == master_email))
            master_user = result.scalar_one_or_none()
            
            if not master_user:
                print(f"   -> Injecting master account: {master_email}")
                master_user = User(
                    email=master_email,
                    hashed_password=get_password_hash("Password@123!"),
                    full_name="Prasun Chakraborty",
                    role="admin",
                    is_active=True
                )
                db.add(master_user)
                await db.commit()
                await db.refresh(master_user)

            # ==========================================
            # 3. SEED RELAY CONFIGURATIONS
            # ==========================================
            print(f"⚙️ Seeding Hardware Nodes for User ID: {master_user.id}...")
            
            # Note: This now includes Relay 41 which caused the NotNullViolationError earlier!
            hardware_nodes = [
                (1, 'Relay 1', 'Main Output'),
                (2, 'Relay 2', 'Secondary Output'),
                (41, 'Living Room Lights', 'Smart Home node for living room lights')
            ]
            
            for relay_id, name, desc in hardware_nodes:
                existing_relay = await db.get(RelayConfig, relay_id)
                if not existing_relay:
                    db.add(RelayConfig(
                        id=relay_id, 
                        name=name, 
                        description=desc, 
                        owner_id=master_user.id  # 🔒 STRICT RELATIONSHIP ENFORCED HERE
                    ))
            await db.commit()

            # ==========================================
            # 4. SEED SENSOR TELEMETRY
            # ==========================================
            print("📊 Generating 24-hour historical sensor telemetry...")
            now = datetime.now(timezone.utc)
            
            # Generates 96 data points (1 reading every 15 minutes for 24 hours)
            for i in range(96):
                timestamp = now - timedelta(minutes=15 * i)
                voltage = round(random.uniform(225.0, 235.0), 2)
                power = round(random.uniform(50.0, 2000.0), 2)
                current = round(power / voltage, 2)
                
                db.add(SensorData(
                    voltage_val=voltage,
                    current_val=current,
                    inst_power_val=power,
                    avg_current_val=current,
                    avg_power_val=power,
                    timestamp=timestamp
                ))

            # ==========================================
            # 5. SEED RELAY ACTIVITY LOGS
            # ==========================================
            print("🔌 Seeding Hardware Action Logs...")
            db.add(RelayLog(relay_id=1, state=True, action_by="System Seed", timestamp=now - timedelta(hours=5)))
            db.add(RelayLog(relay_id=1, state=False, action_by="System Seed", timestamp=now - timedelta(hours=1)))
            db.add(RelayLog(relay_id=41, state=True, action_by="System Seed", timestamp=now - timedelta(minutes=30)))

            # Final Commit
            await db.commit()
            print("✅ Database seeding completed successfully!")

        except Exception as e:
            await db.rollback()
            print(f"❌ Seeding failed: {str(e)}")

if __name__ == "__main__":
    # Windows-specific fix for asyncio loops (Required for asyncpg on Windows)
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(seed_database())