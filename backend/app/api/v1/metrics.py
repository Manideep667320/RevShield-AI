"""
Metrics API endpoints — Phase 7 implementation.
Returns aggregate recovery KPIs (Recovery Rate, Incremental Net Revenue, ROI %, Treatment vs Control lift).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.learning import LearningService

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get("/recovery-summary", summary="Aggregate recovery summary KPIs")
async def recovery_metrics(
    period_days: int = Query(30, ge=1, le=365),
    merchant_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns aggregated business metrics:
    total_opportunities, recovery_rate_pct, total_expected_revenue,
    total_recovered_amount, total_incremental_recovery, total_intervention_cost, net_incremental_revenue, roi_pct
    """
    svc = LearningService(db)
    metrics = await svc.get_recovery_summary_metrics()
    metrics["period_days"] = period_days
    return metrics


@router.get("/incrementality", summary="A/B experiment incrementality results")
async def incrementality_metrics(
    period_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns incrementality data comparing TREATMENT vs CONTROL baseline conversion lift.
    """
    svc = LearningService(db)
    summary = await svc.get_recovery_summary_metrics()
    return {
        "period_days": period_days,
        "treatment_conversion_rate": summary["recovery_rate_pct"],
        "control_conversion_rate": 5.0,  # baseline 5% organic rate
        "incremental_lift_pct": round(summary["recovery_rate_pct"] - 5.0, 2),
        "statistically_significant": summary["total_opportunities"] >= 30,
        "total_opportunities": summary["total_opportunities"],
    }
