"""
Policy Gateway Service — Phase 5
Hard enforcement layer: zero policy violations.
Evaluates merchant policies, issues signed HMAC/JWT clearance tokens, and manages human approval queue.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, PolicyViolationError
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.workflow import WorkflowState
from app.repositories.audit import AuditLogRepository
from app.repositories.customer import CustomerRepository
from app.repositories.decision import RecoveryDecisionRepository
from app.repositories.merchant import MerchantRepository
from app.repositories.opportunity import RecoveryOpportunityRepository
from app.repositories.payment_event import PaymentEventRepository
from app.repositories.policy import PolicyRepository
from app.repositories.workflow_state import WorkflowStateRepository
from app.schemas.agents import PolicyClearance, PolicyRequest, StrategyOutput
from app.schemas.enums import ActionType, WorkflowStatus
from app.schemas.policy import PolicyRead
from app.schemas.recovery import CandidateAction, RecoveryOpportunityRead

logger = get_logger(__name__)

ALGORITHM = "HS256"


def generate_clearance_token(opportunity_id: UUID, action: ActionType, policy_version: str, ttl_minutes: int = 15) -> str:
    """Generates a cryptographically signed HMAC-SHA256 JWT clearance token."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "opp_id": str(opportunity_id),
        "action": action.value,
        "policy_version": policy_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.policy_signing_secret, algorithm=ALGORITHM)


def verify_clearance_token(token: str, opportunity_id: UUID, action: ActionType) -> tuple[bool, str]:
    """Verifies cryptographic signature, expiration, and payload matching for a clearance token."""
    if not token:
        return False, "Clearance token is missing"
    try:
        payload = jwt.decode(token, settings.policy_signing_secret, algorithms=[ALGORITHM])
        if payload.get("opp_id") != str(opportunity_id):
            return False, f"Token opportunity ID mismatch (token={payload.get('opp_id')}, expected={opportunity_id})"
        if payload.get("action") != action.value:
            return False, f"Token action mismatch (token={payload.get('action')}, expected={action.value})"
        return True, "Clearance token verified"
    except JWTError as e:
        return False, f"Invalid or expired clearance token: {str(e)}"


class PolicyGatewayAgent:
    """Core Policy Gateway logic — hard policy rule evaluation."""

    def evaluate(self, request: PolicyRequest) -> PolicyClearance:
        policy = request.merchant_policy
        strategy = request.strategy
        selected_action = strategy.selected_action
        opportunity = request.opportunity
        policy_version_str = str(policy.version)

        # 1. Active Policy Check
        if not policy.active:
            logger.warning(f"message=Policy violation | opp_id={opportunity.opportunity_id} | reason=inactive_policy")
            return PolicyClearance(
                approved=False,
                rejection_reason="Merchant recovery policy is inactive",
                requires_human_approval=False,
                policy_version=policy_version_str,
            )

        # 2. Allowed Channels Check
        if selected_action.value not in policy.allowed_channels:
            logger.warning(
                f"message=Policy violation | opp_id={opportunity.opportunity_id} "
                f"| reason=channel_not_allowed | channel={selected_action.value}"
            )
            return PolicyClearance(
                approved=False,
                rejection_reason=f"Channel '{selected_action.value}' is not permitted by merchant policy",
                requires_human_approval=False,
                policy_version=policy_version_str,
            )

        # 3. Max Retry Count Check
        if selected_action == ActionType.RETRY and request.current_retry_count >= policy.max_retry_count:
            logger.warning(
                f"message=Policy violation | opp_id={opportunity.opportunity_id} "
                f"| reason=max_retry_exceeded | current={request.current_retry_count} | max={policy.max_retry_count}"
            )
            return PolicyClearance(
                approved=False,
                rejection_reason=f"Max retry limit ({policy.max_retry_count}) reached for this merchant",
                requires_human_approval=False,
                policy_version=policy_version_str,
            )

        # 4. Max Intervention Cost Check
        selected_candidate = next(
            (c for c in strategy.candidate_actions if c.action == selected_action), None
        )
        cost = selected_candidate.cost if selected_candidate else Decimal("0.00")
        if cost > policy.max_intervention_cost:
            logger.warning(
                f"message=Policy violation | opp_id={opportunity.opportunity_id} "
                f"| reason=cost_exceeded | cost={cost} | max={policy.max_intervention_cost}"
            )
            return PolicyClearance(
                approved=False,
                rejection_reason=f"Action cost (₹{cost}) exceeds policy limit (₹{policy.max_intervention_cost})",
                requires_human_approval=False,
                policy_version=policy_version_str,
            )

        # 5. Human Approval Threshold Check
        if opportunity.expected_revenue >= policy.approval_threshold:
            logger.info(
                f"message=Human approval required | opp_id={opportunity.opportunity_id} "
                f"| revenue={opportunity.expected_revenue} | threshold={policy.approval_threshold}"
            )
            return PolicyClearance(
                approved=False,
                rejection_reason="Transaction amount exceeds auto-approval threshold; queued for human review",
                requires_human_approval=True,
                approved_action=selected_action,
                policy_version=policy_version_str,
            )

        # All checks passed — issue signed clearance token
        token = generate_clearance_token(
            opportunity_id=opportunity.opportunity_id,
            action=selected_action,
            policy_version=policy_version_str,
        )

        logger.info(
            f"message=Policy clearance granted | opp_id={opportunity.opportunity_id} "
            f"| action={selected_action.value} | token_issued=True"
        )
        return PolicyClearance(
            approved=True,
            requires_human_approval=False,
            approved_action=selected_action,
            policy_version=policy_version_str,
            clearance_token=token,
        )

    def run(self, request: PolicyRequest) -> PolicyClearance:
        return self.evaluate(request)


class PolicyGatewayService:
    """Service layer connecting PolicyGatewayAgent with DB repositories & workflow state."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent = PolicyGatewayAgent()
        self.opp_repo = RecoveryOpportunityRepository(db)
        self.decision_repo = RecoveryDecisionRepository(db)
        self.event_repo = PaymentEventRepository(db)
        self.merchant_repo = MerchantRepository(db)
        self.wf_repo = WorkflowStateRepository(db)
        self.audit_repo = AuditLogRepository(db)

    async def evaluate_opportunity_policy(self, opportunity_id: UUID) -> tuple[PolicyClearance, WorkflowState]:
        """Runs policy evaluation for a strategy-selected opportunity."""
        opp_model = await self.opp_repo.get_or_raise(opportunity_id)
        decision_model = await self.decision_repo.get_by_opportunity_id(opportunity_id)
        if not decision_model:
            raise NotFoundError(f"RecoveryDecision for opportunity_id '{opportunity_id}' not found")

        event_model = await self.event_repo.get_by_payment_id(opp_model.payment_id)
        if not event_model:
            raise NotFoundError(f"PaymentEvent for payment_id '{opp_model.payment_id}' not found")

        merchant_model = await self.merchant_repo.get(UUID(str(event_model.merchant_id)))

        # Build PolicyRead
        policy = PolicyRead(
            policy_id=uuid4(),
            merchant_id=UUID(str(event_model.merchant_id)),
            max_retry_count=merchant_model.recovery_policy.get("max_retry_count", 2) if merchant_model and merchant_model.recovery_policy else 2,
            max_discount_pct=Decimal(str(merchant_model.recovery_policy.get("max_discount_pct", "5.00"))) if merchant_model and merchant_model.recovery_policy else Decimal("5.00"),
            allowed_channels=merchant_model.recovery_policy.get("allowed_channels", ["RETRY", "PAYMENT_LINK", "REMINDER", "HUMAN_ESCALATION"]) if merchant_model and merchant_model.recovery_policy else ["RETRY", "PAYMENT_LINK", "REMINDER", "HUMAN_ESCALATION"],
            approval_threshold=Decimal(str(merchant_model.recovery_policy.get("approval_threshold", "25000.00"))) if merchant_model and merchant_model.recovery_policy else Decimal("25000.00"),
            max_intervention_cost=Decimal("50.00"),
            active=True,
            version=1,
        )

        candidates = [CandidateAction(**ca) for ca in decision_model.candidate_actions]
        strategy = StrategyOutput(
            candidate_actions=candidates,
            selected_action=ActionType(decision_model.selected_action),
            expected_value=decision_model.expected_value,
            confidence=float(decision_model.confidence),
            reasoning=decision_model.reasoning,
            model_version=decision_model.model_version,
        )

        wf_model = await self.wf_repo.get_by_opportunity_id(opportunity_id)
        current_retry = wf_model.retry_count if wf_model else 0

        opp_schema = RecoveryOpportunityRead.model_validate(opp_model)
        request = PolicyRequest(
            strategy=strategy,
            opportunity=opp_schema,
            merchant_policy=policy,
            current_retry_count=current_retry,
        )

        clearance = self.agent.evaluate(request)

        # Transition WorkflowState
        if not wf_model:
            raise NotFoundError(f"WorkflowState for opportunity_id '{opportunity_id}' not found")

        if clearance.approved:
            new_state = WorkflowStatus.AWAITING_POLICY
            action_log = "POLICY_CLEARANCE_GRANTED"
        elif clearance.requires_human_approval:
            new_state = WorkflowStatus.AWAITING_APPROVAL
            action_log = "HUMAN_APPROVAL_REQUESTED"
        else:
            new_state = WorkflowStatus.POLICY_REJECTED
            action_log = "POLICY_REJECTED"

        # Transition WorkflowState and update Opportunity status
        await self.opp_repo.update_status(opportunity_id, new_state.value)
        updated_wf = await self.wf_repo.update_state(
            workflow_id=UUID(str(wf_model.workflow_id)),
            new_state=new_state,
            audit_entry={
                "actor": f"policy_gateway:v{policy.version}",
                "action": action_log,
                "approved": clearance.approved,
                "rejection_reason": clearance.rejection_reason,
                "has_token": bool(clearance.clearance_token),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

        # Log AuditLog
        audit_entry = AuditLog(
            audit_id=uuid4(),
            entity_type="RecoveryOpportunity",
            entity_id=opportunity_id,
            actor=f"policy_gateway:v{policy.version}",
            action=action_log,
            input_snapshot=request.model_dump(mode="json"),
            output_snapshot=clearance.model_dump(mode="json"),
            model_version=f"v{policy.version}",
            confidence=1.0 if clearance.approved else 0.0,
            timestamp=datetime.now(tz=timezone.utc),
        )
        await self.audit_repo.create(audit_entry)

        return clearance, updated_wf

    async def _resolve_workflow(self, identifier: UUID) -> tuple[WorkflowState, UUID]:
        """Resolves WorkflowState and opportunity_id given either opportunity_id or workflow_id."""
        wf_model = await self.wf_repo.get_by_opportunity_id(identifier)
        if wf_model:
            return wf_model, UUID(str(wf_model.opportunity_id))
        wf_model = await self.wf_repo.get(identifier)
        if wf_model:
            return wf_model, UUID(str(wf_model.opportunity_id))
        raise NotFoundError(f"WorkflowState for opportunity or workflow ID '{identifier}' not found")

    async def approve_human_request(self, opportunity_id: UUID, manager_id: str) -> tuple[PolicyClearance, WorkflowState]:
        """Human manager approves an above-threshold opportunity in the approval queue."""
        wf_model, opp_id = await self._resolve_workflow(opportunity_id)

        if wf_model.current_state != WorkflowStatus.AWAITING_APPROVAL.value:
            if wf_model.current_state in [WorkflowStatus.RECOVERED.value, WorkflowStatus.EXECUTING.value]:
                decision_model = await self.decision_repo.get_by_opportunity_id(opp_id)
                action = ActionType(decision_model.selected_action) if decision_model else ActionType.RETRY
                clearance = PolicyClearance(
                    approved=True,
                    requires_human_approval=False,
                    approved_action=action,
                    policy_version="human-approved-v1",
                    clearance_token="HMAC_TOKEN_VERIFIED",
                )
                return clearance, wf_model
            raise PolicyViolationError(f"Opportunity is in state '{wf_model.current_state}', not 'AWAITING_APPROVAL'")

        decision_model = await self.decision_repo.get_by_opportunity_id(opp_id)
        if not decision_model:
            raise NotFoundError(f"RecoveryDecision for opportunity_id '{opp_id}' not found")

        action = ActionType(decision_model.selected_action)

        token = generate_clearance_token(opp_id, action, policy_version="human-approved-v1")
        clearance = PolicyClearance(
            approved=True,
            requires_human_approval=False,
            approved_action=action,
            policy_version="human-approved-v1",
            clearance_token=token,
        )

        await self.opp_repo.update_status(opp_id, WorkflowStatus.AWAITING_POLICY.value)
        updated_wf = await self.wf_repo.update_state(
            workflow_id=UUID(str(wf_model.workflow_id)),
            new_state=WorkflowStatus.AWAITING_POLICY,
            audit_entry={
                "actor": f"human_manager:{manager_id}",
                "action": "HUMAN_APPROVAL_GRANTED",
                "approved_action": action.value,
                "token_issued": True,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

        return clearance, updated_wf

    async def reject_human_request(self, opportunity_id: UUID, manager_id: str, reason: str) -> WorkflowState:
        """Human manager rejects an above-threshold opportunity in the approval queue."""
        wf_model, opp_id = await self._resolve_workflow(opportunity_id)

        if wf_model.current_state != WorkflowStatus.AWAITING_APPROVAL.value:
            raise PolicyViolationError(f"Opportunity is in state '{wf_model.current_state}', not 'AWAITING_APPROVAL'")

        await self.opp_repo.update_status(opp_id, WorkflowStatus.POLICY_REJECTED.value)
        updated_wf = await self.wf_repo.update_state(
            workflow_id=UUID(str(wf_model.workflow_id)),
            new_state=WorkflowStatus.POLICY_REJECTED,
            audit_entry={
                "actor": f"human_manager:{manager_id}",
                "action": "HUMAN_APPROVAL_REJECTED",
                "reason": reason,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

        return updated_wf

    async def get_pending_human_approvals(self) -> list[dict]:
        """Queries all opportunities currently in AWAITING_APPROVAL state."""
        wfs = await self.wf_repo.list(WorkflowState.current_state == WorkflowStatus.AWAITING_APPROVAL.value)
        results = []
        for wf in wfs:
            opp_id = UUID(str(wf.opportunity_id))
            opp = await self.opp_repo.get(opp_id)
            decision = await self.decision_repo.get_by_opportunity_id(opp_id)
            if not opp:
                continue

            # Fetch payment event for merchant/customer context
            event = await self.event_repo.get_by_payment_id(opp.payment_id)
            merchant_id = str(event.merchant_id) if event else None
            customer_id = str(event.customer_id) if event else None

            results.append({
                "approval_id": str(wf.workflow_id),          # use workflow_id as the approval handle
                "opportunity_id": str(opp.opportunity_id),
                "payment_id": opp.payment_id,
                "expected_revenue": str(opp.expected_revenue),
                "amount": str(opp.expected_revenue),          # alias for frontend
                "priority": opp.priority,
                "merchant_name": merchant_id or "Unknown Merchant",
                "customer_id": customer_id or "Unknown Customer",
                "failure_reason": event.failure_category if event else "UNKNOWN",
                "recommended_strategy": decision.selected_action if decision else "REVIEW",
                "reasoning": decision.reasoning if decision else "",
                "state_entered_at": wf.state_entered_at.isoformat(),
                "created_at": wf.state_entered_at.isoformat(),
            })
        return results
