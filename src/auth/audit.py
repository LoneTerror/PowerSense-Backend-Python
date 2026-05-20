import asyncio
from src.database.client import AsyncSessionLocal
from src.database.models import AuditLog
from src.common.email_utils import get_location_from_ip, send_login_alert_email, send_password_reset_email

async def process_login_audit(user_id: int, email: str, full_name: str, ip_address: str):
    """
    Background pipeline: 
    1. Fetches Geolocation
    2. Saves to Database
    3. Triggers the Email
    """
    # 1. Run the blocking API call in a thread so it doesn't freeze the async loop
    location = await asyncio.to_thread(get_location_from_ip, ip_address)

    # 2. Open a fresh DB connection strictly for this background task
    async with AsyncSessionLocal() as db:
        try:
            audit_entry = AuditLog(
                user_id=user_id,
                action="LOGIN_SUCCESS",
                ip_address=ip_address,
                location=location
            )
            db.add(audit_entry)
            await db.commit()
        except Exception as e:
            # If DB fails, we still want to send the security email!
            print(f"❌ Failed to save AuditLog: {e}")

    # 3. Run the blocking SMTP email transmission in a thread
    await asyncio.to_thread(send_login_alert_email, email, full_name, ip_address, location)


async def process_password_reset_request_audit(user_id: int, email: str, full_name: str, ip_address: str, token: str):
    location = await asyncio.to_thread(get_location_from_ip, ip_address)
    async with AsyncSessionLocal() as db:
        try:
            audit_entry = AuditLog(
                user_id=user_id,
                action="PASSWORD_RESET_REQUESTED",
                ip_address=ip_address,
                location=location
            )
            db.add(audit_entry)
            await db.commit()
        except Exception as e:
            print(f"❌ Failed to save AuditLog: {e}")

    # Trigger the reset email
    await asyncio.to_thread(send_password_reset_email, email, full_name, token)


async def process_password_changed_audit(user_id: int, ip_address: str):
    location = await asyncio.to_thread(get_location_from_ip, ip_address)
    async with AsyncSessionLocal() as db:
        try:
            audit_entry = AuditLog(
                user_id=user_id,
                action="PASSWORD_RESET_SUCCESS",
                ip_address=ip_address,
                location=location
            )
            db.add(audit_entry)
            await db.commit()
        except Exception as e:
            print(f"❌ Failed to save AuditLog: {e}")