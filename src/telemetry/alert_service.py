import smtplib
import os
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import User, RelayConfig, Notification
import asyncio

# Fetch credentials directly from your .env file
SMTP_SERVER = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_EMAIL = os.getenv("SMTP_USER")
SENDER_PASSWORD = os.getenv("SMTP_PASSWORD")

def send_email_sync(to_email: str, subject: str, body: str):
    """Sends the email using STARTTLS on port 587."""
    # Safety check so it doesn't crash if you forgot to set the .env variable
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("⚠️ Email skipped: SMTP credentials not configured in .env")
        return

    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email

        # 🚀 THE FIX: Use standard SMTP with STARTTLS for port 587
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls() # Secure the connection
            server.ehlo()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            
        print(f"✅ Alert email successfully sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

async def evaluate_thresholds_and_alert(user_id: int, current_amps: float, current_power_w: float, db: AsyncSession):
    """Evaluates telemetry against user thresholds and triggers alerts."""
    now = datetime.now(timezone.utc)
    
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    relays = (await db.execute(select(RelayConfig).where(RelayConfig.owner_id == user_id))).scalars().all()

    alerts_to_trigger = []

    # 1. Max Sensor Capacity Alert
    if current_amps > 30.0:
        alerts_to_trigger.append({
            "title": "CRITICAL: Sensor Overload",
            "message": f"Total current reached {round(current_amps, 2)}A, exceeding the 30A safe limit! Please reduce load immediately to prevent hardware damage."
        })

    # 2. Appliance Usage Alerts
    for relay in relays:
        if relay.is_on and relay.threshold:
            limit_w = relay.threshold if relay.threshold_unit == "W" else relay.threshold * 230.0 
            if current_power_w > limit_w:
                alerts_to_trigger.append({
                    "title": f"Abnormal Usage: {relay.name}",
                    "message": f"Power usage ({round(current_power_w, 2)}W) exceeded your set limit of {relay.threshold}{relay.threshold_unit}."
                })

    # 3. Process Alerts with a 30-Minute Debounce
    for alert in alerts_to_trigger:
        recent_alert_query = (
            select(Notification)
            .where(Notification.owner_id == user_id)
            .where(Notification.title == alert["title"])
            .where(Notification.timestamp > now - timedelta(minutes=30))
        )
        recent_alert = (await db.execute(recent_alert_query)).scalars().first()

        if not recent_alert:
            # Save to Database (In-App Notification)
            new_notif = Notification(
                owner_id=user_id,
                title=alert["title"],
                message=alert["message"],
                timestamp=now
            )
            db.add(new_notif)
            
            # Fire the email asynchronously
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, send_email_sync, user.email, alert["title"], alert["message"])
            
    await db.commit()