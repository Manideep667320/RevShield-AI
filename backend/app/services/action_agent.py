"""
Action Agent & Service — Phase 6
Executes approved recovery interventions after strict clearance token verification.
Persists Intervention records, manages workflow state transitions, and writes audit trails.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PolicyViolationError
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.recovery import Intervention
from app.models.workflow import WorkflowState
from app.repositories.audit import AuditLogRepository
from app.repositories.decision import RecoveryDecisionRepository
from app.repositories.intervention import InterventionRepository
from app.repositories.opportunity import RecoveryOpportunityRepository
from app.repositories.payment_event import PaymentEventRepository
from app.repositories.workflow_state import WorkflowStateRepository
from app.schemas.agents import ActionRequest, ActionResponse, PolicyClearance
from app.schemas.enums import ActionType, WorkflowStatus
from app.services.policy_gateway import verify_clearance_token
from app.services.razorpay_client import RazorpayResult, RazorpaySandboxClient

logger = get_logger(__name__)


class ActionAgent:
    """Core Action Agent — verifies clearance tokens and dispatches to Razorpay sandbox."""

    def __init__(self, razorpay_client: RazorpaySandboxClient | None = None):
        self.razorpay_client = razorpay_client or RazorpaySandboxClient()

    def execute_action(self, request: ActionRequest) -> tuple[ActionResponse, Decimal]:
        """
        1. Verifies signed clearance token
        2. Dispatches action to Razorpay sandbox client
        3. Returns ActionResponse and intervention cost
        """
        # Strict Clearance Token Signature Verification
        token = request.clearance.clearance_token
        valid, err_msg = verify_clearance_token(token, request.opportunity_id, request.action_type)
        if not valid:
            logger.error(
                f"message=Action execution blocked | opp_id={request.opportunity_id} "
                f"| reason=invalid_clearance_token | details={err_msg}"
            )
            raise PolicyViolationError(f"Clearance token verification failed: {err_msg}")

        action_type = request.action_type
        cost = Decimal("0.00")

        if action_type == ActionType.RETRY:
            cost = Decimal("0.00")
            result = self.razorpay_client.retry_payment(request.payment_details.get("payment_id", ""))
        elif action_type == ActionType.PAYMENT_LINK:
            cost = Decimal("2.00")
            amount = Decimal(str(request.payment_details.get("amount", "0.00")))
            email = request.customer_contact.get("email", "")
            phone = request.customer_contact.get("phone", "")
            result = self.razorpay_client.create_payment_link(amount=amount, customer_email=email, customer_phone=phone)
        elif action_type == ActionType.REMINDER:
            cost = Decimal("0.50")
            phone = request.customer_contact.get("phone", "")
            result = self.razorpay_client.send_reminder(customer_phone=phone)
        elif action_type == ActionType.HUMAN_ESCALATION:
            cost = Decimal("50.00")
            result = self.razorpay_client.escalate_to_human(request.opportunity_id, reasoning="Manual ops review required")
        elif action_type == ActionType.NO_ACTION:
            cost = Decimal("0.00")
            result = RazorpayResult(
                success=True,
                external_ref="no_op",
                status="NO_ACTION",
                message="No intervention executed per strategy",
                action_type=ActionType.NO_ACTION,
            )
        else:
            raise ValueError(f"Unsupported action type: {action_type}")

        now = datetime.now(tz=timezone.utc)
        response = ActionResponse(
            success=result.success,
            intervention_id=uuid4(),
            external_ref=result.external_ref,
            status=result.status,
            error_message=result.message if not result.success else None,
            executed_at=now,
        )

        logger.info(
            f"message=Action executed | opp_id={request.opportunity_id} | action={action_type.value} "
            f"| success={response.success} | ref={response.external_ref}"
        )

        return response, cost


class ActionService:
    """Service layer connecting ActionAgent with DB repositories & workflow state."""

    def __init__(self, db: AsyncSession, razorpay_client: RazorpaySandboxClient | None = None):
        self.db = db
        self.agent = ActionAgent(razorpay_client=razorpay_client)
        self.opp_repo = RecoveryOpportunityRepository(db)
        self.decision_repo = RecoveryDecisionRepository(db)
        self.intervention_repo = InterventionRepository(db)
        self.event_repo = PaymentEventRepository(db)
        self.wf_repo = WorkflowStateRepository(db)
        self.audit_repo = AuditLogRepository(db)

    async def execute_opportunity_intervention(
        self, opportunity_id: UUID, clearance_token: str
    ) -> tuple[ActionResponse, Intervention, WorkflowState]:
        """
        Executes approved intervention for an opportunity:
        1. Loads opportunity, decision, and payment event
        2. Constructs ActionRequest with PolicyClearance token
        3. Invokes ActionAgent
        4. Persists Intervention ORM record
        5. Updates WorkflowState state & audit entry
        6. Writes AuditLog record
        """
        opp_model = await self.opp_repo.get_or_raise(opportunity_id)
        decision_model = await self.decision_repo.get_by_opportunity_id(opportunity_id)
        if not decision_model:
            raise NotFoundError(f"RecoveryDecision for opportunity_id '{opportunity_id}' not found")

        event_model = await self.event_repo.get_by_payment_id(opp_model.payment_id)
        action_type = ActionType(decision_model.selected_action)

        clearance = PolicyClearance(
            approved=True,
            requires_human_approval=False,
            approved_action=action_type,
            policy_version="verified-v1",
            clearance_token=clearance_token,
        )

        action_request = ActionRequest(
            opportunity_id=opportunity_id,
            action_type=action_type,
            clearance=clearance,
            customer_contact={"email": "customer@example.com", "phone": "+919876543210"},
            payment_details={"payment_id": opp_model.payment_id, "amount": str(opp_model.expected_revenue)},
            idempotency_key=f"action-{opportunity_id}",
        )

        response, cost = self.agent.execute_action(action_request)

        # Persist Intervention ORM record
        intervention_model = Intervention(
            intervention_id=response.intervention_id,
            decision_id=decision_model.decision_id,
            type=action_type.value,
            status=response.status,
            executed_at=response.executed_at,
            cost=cost,
            external_ref=response.external_ref,
        )
        intervention = await self.intervention_repo.create(intervention_model)

        # Transition WorkflowState
        wf = await self.wf_repo.get_by_opportunity_id(opportunity_id)
        if not wf:
            raise NotFoundError(f"WorkflowState for opportunity_id '{opportunity_id}' not found")

        new_state = WorkflowStatus.EXECUTING if response.success else WorkflowStatus.FAILED
        action_log = "ACTION_EXECUTED" if response.success else "ACTION_FAILED"

        # Transition WorkflowState and update Opportunity status
        await self.opp_repo.update_status(opportunity_id, new_state.value)
        updated_wf = await self.wf_repo.update_state(
            workflow_id=UUID(str(wf.workflow_id)),
            new_state=new_state,
            audit_entry={
                "actor": f"action_agent:{action_type.value}",
                "action": action_log,
                "success": response.success,
                "external_ref": response.external_ref,
                "cost": str(cost),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

        # Log AuditLog
        audit_entry = AuditLog(
            audit_id=uuid4(),
            entity_type="RecoveryOpportunity",
            entity_id=opportunity_id,
            actor=f"action_agent:{action_type.value}",
            action=action_log,
            input_snapshot=action_request.model_dump(mode="json"),
            output_snapshot=response.model_dump(mode="json"),
            model_version="v1.0",
            confidence=1.0 if response.success else 0.0,
            timestamp=datetime.now(tz=timezone.utc),
        )
        await self.audit_repo.create(audit_entry)

        return response, intervention, updated_wf
