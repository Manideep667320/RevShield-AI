"""
Temporal Workflow Activities — Phase 6
Executes individual pipeline steps as idempotent, retryable Temporal activities.
Supports optional db session parameter for unit test execution.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity
from app.core.database import AsyncSessionLocal
from app.models.payment_event import PaymentEvent
from app.repositories.payment_event import PaymentEventRepository
from app.schemas.agents import DetectionInput
from app.schemas.customer import CustomerContext
from app.schemas.payment_event import PaymentEventRead
from app.schemas.policy import PolicyRead
from app.services.action_agent import ActionService
from app.services.detection import DetectionService
from app.services.diagnosis import DiagnosisService
from app.services.policy_gateway import PolicyGatewayService
from app.services.strategy import StrategyService


@activity.defn
async def detect_activity(input_dict: dict, db: AsyncSession | None = None) -> dict:
    """Detection Agent activity."""
    async def _run(session: AsyncSession):
        svc = DetectionService(session)
        if "payment_event" in input_dict:
            det_input = DetectionInput(**input_dict)
        else:
            event_id = UUID(input_dict["event_id"]) if "event_id" in input_dict else uuid4()
            merchant_id = UUID(input_dict["merchant_id"]) if "merchant_id" in input_dict else uuid4()
            customer_id = UUID(input_dict["customer_id"]) if "customer_id" in input_dict else uuid4()

            pe = PaymentEventRead(
                event_id=event_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
                payment_id=input_dict["payment_id"],
                amount=Decimal(str(input_dict.get("amount", "1000.00"))),
                currency=input_dict.get("currency", "INR"),
                payment_method=input_dict.get("payment_method", "CARD"),
                status=input_dict.get("status", "failed"),
                failure_code=input_dict.get("failure_code", "GATEWAY_ERROR"),
                failure_category="TEMPORARY_FAILURE",
                timestamp=input_dict.get("timestamp"),
            )
            cust = CustomerContext(
                customer_id=customer_id,
                historical_payment_count=5,
                successful_payment_count=4,
                average_transaction_value=Decimal("1500.00"),
                risk_score=0.20,
            )
            policy = PolicyRead(
                policy_id=uuid4(),
                merchant_id=merchant_id,
                max_retry_count=2,
                max_discount_pct=Decimal("5.00"),
                allowed_channels=["RETRY", "PAYMENT_LINK", "REMINDER"],
                approval_threshold=Decimal("25000.00"),
                max_intervention_cost=Decimal("50.00"),
                active=True,
                version=1,
            )
            det_input = DetectionInput(
                payment_event=pe,
                customer_context=cust,
                merchant_policy=policy,
            )

        # Ensure PaymentEvent exists in DB for downstream agents
        event_repo = PaymentEventRepository(session)
        existing_event = await event_repo.get_by_payment_id(det_input.payment_event.payment_id)
        if not existing_event:
            event_model = PaymentEvent(
                event_id=uuid4(),
                merchant_id=str(det_input.payment_event.merchant_id),
                customer_id=str(det_input.payment_event.customer_id),
                payment_id=det_input.payment_event.payment_id,
                amount=det_input.payment_event.amount,
                currency=det_input.payment_event.currency,
                payment_method=det_input.payment_event.payment_method,
                status=det_input.payment_event.status,
                failure_code=det_input.payment_event.failure_code,
                failure_category=det_input.payment_event.failure_category or "TEMPORARY_FAILURE",
                timestamp=datetime.now(tz=timezone.utc),
                metadata_={},
            )
            await event_repo.create_idempotent(event_model)

        output, opp, wf = await svc.detect_and_create_opportunity(det_input)
        return {
            "eligible": output.eligible,
            "opportunity_id": str(opp.opportunity_id) if opp else None,
            "workflow_id": str(wf.workflow_id) if wf else None,
        }

    if db:
        return await _run(db)
    async with AsyncSessionLocal() as session:
        return await _run(session)


@activity.defn
async def diagnose_activity(opportunity_id_str: str, db: AsyncSession | None = None) -> dict:
    """Diagnosis Agent activity."""
    async def _run(session: AsyncSession):
        svc = DiagnosisService(session)
        opp_id = UUID(opportunity_id_str)
        diagnosis, wf = await svc.diagnose_opportunity(opp_id)
        return {
            "cause": diagnosis.cause.value,
            "confidence": diagnosis.confidence,
            "workflow_state": wf.current_state,
        }

    if db:
        return await _run(db)
    async with AsyncSessionLocal() as session:
        return await _run(session)


@activity.defn
async def select_strategy_activity(opportunity_id_str: str, db: AsyncSession | None = None) -> dict:
    """Recovery Strategy Engine activity."""
    async def _run(session: AsyncSession):
        svc = StrategyService(session)
        opp_id = UUID(opportunity_id_str)
        strategy, decision, wf = await svc.select_strategy_for_opportunity(opp_id)
        return {
            "selected_action": strategy.selected_action.value,
            "expected_value": str(strategy.expected_value),
            "decision_id": str(decision.decision_id),
            "workflow_state": wf.current_state,
        }

    if db:
        return await _run(db)
    async with AsyncSessionLocal() as session:
        return await _run(session)


@activity.defn
async def evaluate_policy_activity(opportunity_id_str: str, db: AsyncSession | None = None) -> dict:
    """Policy Gateway activity."""
    async def _run(session: AsyncSession):
        svc = PolicyGatewayService(session)
        opp_id = UUID(opportunity_id_str)
        clearance, wf = await svc.evaluate_opportunity_policy(opp_id)
        return {
            "approved": clearance.approved,
            "requires_human_approval": clearance.requires_human_approval,
            "clearance_token": clearance.clearance_token,
            "rejection_reason": clearance.rejection_reason,
            "workflow_state": wf.current_state,
        }

    if db:
        return await _run(db)
    async with AsyncSessionLocal() as session:
        return await _run(session)


@activity.defn
async def execute_action_activity(opportunity_id_str: str, clearance_token: str, db: AsyncSession | None = None) -> dict:
    """Action Agent activity."""
    async def _run(session: AsyncSession):
        svc = ActionService(session)
        opp_id = UUID(opportunity_id_str)
        response, intervention, wf = await svc.execute_opportunity_intervention(opp_id, clearance_token)
        return {
            "success": response.success,
            "external_ref": response.external_ref,
            "intervention_id": str(intervention.intervention_id),
            "workflow_state": wf.current_state,
        }

    if db:
        return await _run(db)
    async with AsyncSessionLocal() as session:
        return await _run(session)
