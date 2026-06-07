import calendar
from datetime import datetime, timedelta, timezone, date
from sqlalchemy import select, func
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from src.auth.dependencies import get_current_user_id, get_current_token_payload
from src.database.client import get_db
from src.database.models import MLPrediction, DailyEnergySummary, MonthlyEnergySummary, ConsumptionTarget, TariffPlan
from src.telemetry.schemas import TariffUpdate, TargetUpdate

router = APIRouter(
    prefix="/v1/insights",
    tags=["Machine Learning & Insights"],
    dependencies=[Depends(get_current_token_payload)]
)

# ==========================================
# USER SETTINGS ENDPOINTS
# ==========================================

@router.get("/settings/tariff")
async def get_user_tariff(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Fetches the user's currently active electricity rate. Returns null if not set."""
    try:
        query = select(TariffPlan).where(TariffPlan.owner_id == user_id).order_by(TariffPlan.id.desc()).limit(1)
        tariff = (await db.execute(query)).scalar_one_or_none()

        return {
            # 👇 Now returns None (null in JSON) if the user hasn't set a tariff
            "rate_per_kwh": tariff.rate_per_kwh if tariff else None,
            "currency": tariff.currency if tariff else "INR"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch tariff: {str(e)}")

@router.post("/settings/tariff")
async def update_user_tariff(
    data: TariffUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Allows the user to set their custom electricity rate.
    Inserts a new row to preserve historical billing accuracy.
    """
    try:
        new_tariff = TariffPlan(
            owner_id=user_id,
            rate_per_kwh=data.rate_per_kwh,
            currency=data.currency,
            effective_from=datetime.now(timezone.utc)
        )
        db.add(new_tariff)
        await db.commit()
        
        return {
            "status": "success", 
            "message": f"Rate updated to {data.rate_per_kwh} {data.currency}/kWh",
            "rate_per_kwh": data.rate_per_kwh
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update tariff: {str(e)}")


@router.post("/settings/target")
async def update_user_target(
    data: TargetUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Allows the user to update their monthly budget and kWh limit."""
    try:
        now = datetime.now(timezone.utc)
        
        new_target = ConsumptionTarget(
            owner_id=user_id,
            target_monthly_kwh=data.target_monthly_kwh,
            target_monthly_cost=data.target_monthly_cost,
            valid_for_month=now.month,
            valid_for_year=now.year
        )
        db.add(new_target)
        await db.commit()
        
        return {
            "status": "success", 
            "message": "Monthly targets updated successfully."
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update target: {str(e)}")

# ==========================================
# FETCH DATA ENDPOINTS
# ==========================================

@router.get("/digest")
async def get_ml_digest(
    user_id: int = Depends(get_current_user_id), 
    db: AsyncSession = Depends(get_db)
):
    """Fetches the latest XGBoost prediction and current user budget."""
    try:
        # Get the absolute latest prediction
        pred_query = select(MLPrediction).where(MLPrediction.owner_id == user_id).order_by(MLPrediction.predicted_at.desc()).limit(1)
        prediction = (await db.execute(pred_query)).scalar_one_or_none()

        # Get current active targets
        target_query = select(ConsumptionTarget).where(ConsumptionTarget.owner_id == user_id).order_by(ConsumptionTarget.id.desc()).limit(1)
        target = (await db.execute(target_query)).scalar_one_or_none()

        if not prediction:
            return {"status": "pending", "message": "ML Model is gathering data. Check back tomorrow."}

        return {
            "status": "active",
            "prediction": {
                "predicted_cost_eod": prediction.predicted_cost_eod,
                "predicted_cost_eom": prediction.predicted_cost_eom,
                "required_daily_reduction_kwh": prediction.required_daily_reduction_kwh,
                "model_version": prediction.model_version,
                "predicted_at": prediction.predicted_at
            },
            "target": {
                "monthly_kwh": target.target_monthly_kwh if target else None,
                "monthly_budget": target.target_monthly_cost if target else None
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/daily-history")
async def get_daily_history(
    days: int = 7, 
    user_id: int = Depends(get_current_user_id), 
    db: AsyncSession = Depends(get_db)
):
    """
    Fetches pre-calculated daily summaries. 
    Returns the exact calculated averages and totals, avoiding raw data processing.
    """
    try:
        query = (
            select(DailyEnergySummary)
            .where(DailyEnergySummary.owner_id == user_id)
            .order_by(DailyEnergySummary.summary_date.desc())
            .limit(days)
        )
        records = (await db.execute(query)).scalars().all()
        
        return [
            {
                "date": rec.summary_date,
                "total_kwh": rec.total_kwh,         # Calculated Total Daily Energy
                "avg_power_w": rec.avg_power_w,     # Calculated Average Daily Power
                "peak_power_w": rec.peak_power_w,   # Calculated Max Power Spike
                "total_cost": rec.total_cost
            } for rec in records
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch daily history: {str(e)}")

@router.get("/custom-range")
async def get_custom_range_summary(
    start_date: date,
    end_date: date,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetches aggregated metrics (Total, Avg, Peak, Cost) for a specific date range.
    Also returns the daily breakdown for graphing purposes.
    """
    try:
        # 1. Database-Level Aggregation (Lightning Fast)
        agg_query = select(
            func.sum(DailyEnergySummary.total_kwh).label("total_kwh"),
            func.sum(DailyEnergySummary.total_cost).label("total_cost"),
            func.max(DailyEnergySummary.peak_power_w).label("peak_power"),
            func.avg(DailyEnergySummary.avg_power_w).label("avg_power")
        ).where(
            DailyEnergySummary.owner_id == user_id,
            DailyEnergySummary.summary_date >= start_date,
            DailyEnergySummary.summary_date <= end_date
        )
        
        agg_result = (await db.execute(agg_query)).one_or_none()
        
        # 2. Fetch the daily breakdown for the UI charts
        daily_query = (
            select(DailyEnergySummary)
            .where(
                DailyEnergySummary.owner_id == user_id,
                DailyEnergySummary.summary_date >= start_date,
                DailyEnergySummary.summary_date <= end_date
            )
            .order_by(DailyEnergySummary.summary_date.asc()) # Ascending order is better for line charts
        )
        
        daily_records = (await db.execute(daily_query)).scalars().all()

        # 3. Handle Empty Ranges (If the user picks a future date or date with no data)
        if not agg_result or agg_result.total_kwh is None:
            return {
                "summary": {
                    "total_kwh": 0.0,
                    "total_cost": 0.0,
                    "peak_power_w": 0.0,
                    "avg_power_w": 0.0
                },
                "daily_breakdown": []
            }

        # 4. Return the beautifully formatted JSON
        return {
            "summary": {
                "total_kwh": round(agg_result.total_kwh, 2),
                "total_cost": round(agg_result.total_cost, 2),
                "peak_power_w": round(agg_result.peak_power, 2),
                "avg_power_w": round(agg_result.avg_power, 2)
            },
            "daily_breakdown": [
                {
                    "date": rec.summary_date,
                    "total_kwh": rec.total_kwh,
                    "avg_power_w": rec.avg_power_w,
                    "peak_power_w": rec.peak_power_w,
                    "total_cost": rec.total_cost
                } for rec in daily_records
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch custom range: {str(e)}")

@router.get("/ml-features")
async def get_ml_features(
    target_date: date = None, # Allows fetching historical features for training
    user_id: int = Depends(get_current_user_id), 
    db: AsyncSession = Depends(get_db)
):
    """
    Feature Extraction Engine for the XGBoost ML Model.
    Computes rolling averages, calendar constraints, and target labels.
    """
    try:
        # Default to today if no date is provided
        calc_date = target_date if target_date else datetime.now(timezone.utc).date()
        
        # 1. Calendar Features
        day_of_month = calc_date.day
        month_number = calc_date.month
        year = calc_date.year
        days_in_month = calendar.monthrange(year, month_number)[1]
        days_remaining = days_in_month - day_of_month

        # 2. Tariff & Targets
        tariff = (await db.execute(select(TariffPlan).where(TariffPlan.owner_id == user_id).order_by(TariffPlan.id.desc()).limit(1))).scalar_one_or_none()
        target = (await db.execute(select(ConsumptionTarget).where(ConsumptionTarget.owner_id == user_id).order_by(ConsumptionTarget.id.desc()).limit(1))).scalar_one_or_none()
        
        rate_per_kwh = tariff.rate_per_kwh if tariff else 8.0
        target_monthly_kwh = target.target_monthly_kwh if target else 0.0

        # 3. Monthly Aggregations (Up to the calc_date)
        # Fetch all daily summaries for the current month up to 'calc_date'
        start_of_month = date(year, month_number, 1)
        monthly_query = select(DailyEnergySummary).where(
            DailyEnergySummary.owner_id == user_id,
            DailyEnergySummary.summary_date >= start_of_month,
            DailyEnergySummary.summary_date <= calc_date
        )
        monthly_records = (await db.execute(monthly_query)).scalars().all()

        energy_consumed_so_far_kwh = sum(r.total_kwh for r in monthly_records)
        peak_power_w_this_month = max([r.peak_power_w for r in monthly_records] + [0.0])
        
        # Prevent division by zero on the 1st of the month
        avg_daily_kwh_this_month = energy_consumed_so_far_kwh / day_of_month if day_of_month > 0 else 0.0

        # 4. Rolling Averages (Last 3 and 7 days)
        seven_days_ago = calc_date - timedelta(days=7)
        rolling_query = select(DailyEnergySummary).where(
            DailyEnergySummary.owner_id == user_id,
            DailyEnergySummary.summary_date > seven_days_ago,
            DailyEnergySummary.summary_date <= calc_date
        ).order_by(DailyEnergySummary.summary_date.desc())
        
        rolling_records = (await db.execute(rolling_query)).scalars().all()
        
        # Calculate 7-day avg
        last_7_days_kwh = sum(r.total_kwh for r in rolling_records)
        last_7_days_avg_kwh = last_7_days_kwh / len(rolling_records) if rolling_records else 0.0
        
        # Calculate 3-day avg
        last_3_records = rolling_records[:3]
        last_3_days_kwh = sum(r.total_kwh for r in last_3_records)
        last_3_days_avg_kwh = last_3_days_kwh / len(last_3_records) if last_3_records else 0.0

        # 5. The Training Label (Ground Truth)
        # We only have the true 'total_cost' if the month has ended. 
        # If querying a past month, fetch it from MonthlyEnergySummary.
        label_total_cost = None
        if calc_date < date.today() and day_of_month == days_in_month:
             month_truth = (await db.execute(select(MonthlyEnergySummary).where(
                 MonthlyEnergySummary.owner_id == user_id,
                 MonthlyEnergySummary.month == month_number,
                 MonthlyEnergySummary.year == year
             ))).scalar_one_or_none()
             label_total_cost = month_truth.total_cost if month_truth else None

        # Return the EXACT feature vector Claude requested
        return {
            "features": {
                "day_of_month": day_of_month,
                "days_remaining": days_remaining,
                "month_number": month_number,
                "energy_consumed_so_far_kwh": round(energy_consumed_so_far_kwh, 2),
                "avg_daily_kwh_this_month": round(avg_daily_kwh_this_month, 2),
                "last_7_days_avg_kwh": round(last_7_days_avg_kwh, 2),
                "last_3_days_avg_kwh": round(last_3_days_avg_kwh, 2),
                "peak_power_w_this_month": round(peak_power_w_this_month, 2),
                "rate_per_kwh": rate_per_kwh,
                "target_monthly_kwh": target_monthly_kwh
            },
            "label": {
                "total_cost": label_total_cost # Will be populated for historical end-of-month queries
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))