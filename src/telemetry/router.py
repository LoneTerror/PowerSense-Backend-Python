from fastapi import APIRouter, Depends, HTTPException
from src.auth.dependencies import get_current_token_payload
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.client import get_db
from src.telemetry.schemas import SensorDataResponse
from src.telemetry import service

# Aligned with the /v1/ convention
router = APIRouter(
    prefix="/v1/sensors",
    tags=["Telemetry"],
    dependencies=[Depends(get_current_token_payload)] # THIS LOCKS EVERY ROUTE, UNLOCKS ONLY WHEN THE TOKEN IS PASSED
)

@router.get("/latest", response_model=SensorDataResponse)
async def get_latest_sensors(db: AsyncSession = Depends(get_db)):
    """Fetch instantaneous telemetry for Android Home Screen"""
    try:
        data = await service.get_latest_telemetry(db)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))