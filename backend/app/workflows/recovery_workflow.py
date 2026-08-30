"""
Temporal Recovery Workflow — Phase 6
Orchestrates end-to-end recovery pipeline:
  Detect -> Diagnose -> Select Strategy -> Evaluate Policy -> (Human Approval Signal if needed) -> Execute Action
Guarantees Temporal idempotency (workflow_id = recovery-{opp_id}).
"""
from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import (
        detect_activity,
        diagnose_activity,
        select_strategy_activity,
        evaluate_policy_activity,
        execute_action_activity,
    )


@workflow.defn
class RecoveryWorkflow:

    def __init__(self):
        self.human_approval_received: bool | None = None
        self.approved_token: str = ""

    @workflow.signal
    def receive_human_approval(self, decision_data: dict) -> None:
        """Signal handler for human manager approval or rejection."""
        self.human_approval_received = decision_data.get("approved", False)
        self.approved_token = decision_data.get("token", "")

    @workflow.run
    async def run(self, payment_event_dict: dict) -> dict:
        activity_timeout = timedelta(seconds=15)

        # 1. Detect
        det_res = await workflow.execute_activity(
            detect_activity,
            payment_event_dict,
            start_to_close_timeout=activity_timeout,
        )
        if not det_res.get("eligible") or not det_res.get("opportunity_id"):
            return {"status": "SKIPPED_INELIGIBLE", "details": det_res}

        opp_id = det_res["opportunity_id"]

        # 2. Diagnose
        diag_res = await workflow.execute_activity(
            diagnose_activity,
            opp_id,
            start_to_close_timeout=activity_timeout,
        )

        # 3. Select Strategy
        strat_res = await workflow.execute_activity(
            select_strategy_activity,
            opp_id,
            start_to_close_timeout=activity_timeout,
        )

        # 4. Evaluate Policy
        policy_res = await workflow.execute_activity(
            evaluate_policy_activity,
            opp_id,
            start_to_close_timeout=activity_timeout,
        )

        token = policy_res.get("clearance_token", "")

        # Pause workflow if human approval required
        if policy_res.get("requires_human_approval"):
            await workflow.wait_condition(lambda: self.human_approval_received is not None)
            if not self.human_approval_received:
                return {
                    "status": "POLICY_REJECTED_BY_HUMAN",
                    "opportunity_id": opp_id,
                    "reason": "Rejected by human manager",
                }
            token = self.approved_token

        if not token and not policy_res.get("approved"):
            return {
                "status": "POLICY_REJECTED",
                "opportunity_id": opp_id,
                "reason": policy_res.get("rejection_reason"),
            }

        # 5. Execute Action
        action_res = await workflow.execute_activity(
            execute_action_activity,
            args=[opp_id, token],
            start_to_close_timeout=activity_timeout,
        )

        return {
            "status": "INTERVENTION_EXECUTED" if action_res.get("success") else "INTERVENTION_FAILED",
            "opportunity_id": opp_id,
            "external_ref": action_res.get("external_ref"),
            "workflow_state": action_res.get("workflow_state"),
        }
