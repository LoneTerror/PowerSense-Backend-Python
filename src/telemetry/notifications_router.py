from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

# Import your auth dependencies and database models
from src.auth.dependencies import get_current_token_payload, get_current_user_id
from src.database.client import get_db
from src.database.models import Notification

# Create the router instance
router = APIRouter(
    prefix="/v1/notifications",
    tags=["Notifications"],
    dependencies=[Depends(get_current_token_payload)]
)

# Define the Pydantic schema for the update request
class NotificationUpdate(BaseModel):
    is_read: bool

@router.get("/")
async def get_notifications(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Fetch all notifications for the authenticated user, sorted by newest first."""
    try:
        query = (
            select(Notification)
            .where(Notification.owner_id == user_id)
            .order_by(Notification.timestamp.desc())
        )
        logs = (await db.execute(query)).scalars().all()
        
        return [
            {
                "id": n.id, 
                "title": n.title, 
                "message": n.message, 
                "is_read": n.is_read, 
                "timestamp": n.timestamp
            } 
            for n in logs
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch notifications: {str(e)}")

@router.put("/{notif_id}/read")
async def mark_notification_read(
    notif_id: int, 
    update: NotificationUpdate, 
    user_id: int = Depends(get_current_user_id), 
    db: AsyncSession = Depends(get_db)
):
    """Mark a specific notification as read or unread."""
    try:
        query = select(Notification).where(
            Notification.id == notif_id, 
            Notification.owner_id == user_id
        )
        notif = (await db.execute(query)).scalar_one_or_none()
        
        if notif:
            notif.is_read = update.is_read
            await db.commit()
            return {"success": True, "message": "Notification updated"}
        else:
            raise HTTPException(status_code=404, detail="Notification not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update notification: {str(e)}")