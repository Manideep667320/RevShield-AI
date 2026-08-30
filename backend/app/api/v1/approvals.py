"""
Human Approval Queue API endpoints — Phase 5 implementation.
Manages manual reviews for recovery decisions exceeding policy auto-approval thresholds.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.policy_gateway import PolicyGatewayService

router = APIRouter(prefix="/approvals", tags=["Human Approvals"])


class ApprovalDecision(BaseModel):
    approved: bool
    reviewer_id: str = Field(..., description="ID or email of approving manager")
    notes: str | None = Field(None, description="Optional reviewer feedback")


@router.get("", summary="List pending human approvals")
async def list_pending_approvals(db: AsyncSession = Depends(get_db)):
    """Returns list of opportunities currently awaiting human manager approval."""
    svc = PolicyGatewayService(db)
    pending = await svc.get_pending_human_approvals()
    return {"pending_count": len(pending), "opportunities": pending}


@router.post("/{opportunity_id}/approve", summary="Approve a pending recovery decision")
async def approve_recovery_decision(
    opportunity_id: UUID,
    body: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
):
    """
    Human manager approves an above-threshold recovery opportunity.
    Issues signed HMAC clearance token, executes intervention action, and records recovery outcome.
    """
    from app.services.action_agent import ActionService
    from app.services.learning import LearningService

    policy_svc = PolicyGatewayService(db)
    clearance, wf = await policy_svc.approve_human_request(opportunity_id, manager_id=body.reviewer_id)

    # Execute Stage 5: ACTION
    action_svc = ActionService(db)
    action_res, intervention, action_wf = await action_svc.execute_opportunity_intervention(
        opportunity_id=opportunity_id,
        clearance_token=clearance.clearance_token,
    )

    # Execute Stage 6: OUTCOME
    learning_svc = LearningService(db)
    attrib_res, outcome, final_wf = await learning_svc.record_opportunity_outcome(
        opportunity_id=opportunity_id,
        payment_status="captured" if action_res.success else "failed",
    )

    return {
        "status": "APPROVED",
        "clearance": clearance,
        "workflow_id": str(final_wf.workflow_id),
        "workflow_state": final_wf.current_state,
        "recovered_amount": str(attrib_res.recovered_amount),
    }


@router.post("/{opportunity_id}/reject", summary="Reject a pending recovery decision")
async def reject_recovery_decision(
    opportunity_id: UUID,
    body: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
):
    """
    Human manager rejects an above-threshold recovery opportunity.
    Advances workflow state to POLICY_REJECTED.
    """
    svc = PolicyGatewayService(db)
    reason = body.notes or "Rejected by human manager"
    wf = await svc.reject_human_request(opportunity_id, manager_id=body.reviewer_id, reason=reason)
    return {
        "status": "REJECTED",
        "workflow_id": str(wf.workflow_id),
        "workflow_state": wf.current_state,
        "reason": reason,
    }
