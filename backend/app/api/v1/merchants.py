from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas import PolicyRead, PolicyUpdate

router = APIRouter(prefix="/merchants", tags=["Merchants"])


@router.get("/{merchant_id}/policy", response_model=PolicyRead, summary="Get merchant recovery policy")
async def get_merchant_policy(merchant_id: UUID, db: AsyncSession = Depends(get_db)):
    """Returns the active recovery policy for a merchant."""
    # Phase 5: policy repository lookup wired here
    return {}


@router.put("/{merchant_id}/policy", response_model=PolicyRead, summary="Update merchant recovery policy")
async def update_merchant_policy(
    merchant_id: UUID,
    update: PolicyUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Updates merchant recovery policy. Creates new version — old version preserved.
    Policy changes take effect on next workflow execution.
    """
    # Phase 5: policy versioning wired here
    return {}


@router.post(
    "/simulate-payment",
    summary="Inject synthetic payment failure event (dev/test only)",
    tags=["Development"],
)
async def simulate_payment_failure(db: AsyncSession = Depends(get_db)):
    """
    Injects a synthetic failed payment event for testing the recovery pipeline.
    Only available in development environment.
    """
    # Phase 1: simulator wired here
    return {"status": "simulated"}
