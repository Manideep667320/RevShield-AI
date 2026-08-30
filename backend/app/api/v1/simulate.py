"""
Simulate endpoint — injects synthetic failed payment events for dev/test.
Only active in non-production environments.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.schemas.payment_event import SimulatePaymentRequest
from app.services.payment_event import PaymentEventService

router = APIRouter(prefix="/simulate", tags=["Development / Simulation"])
logger = get_logger(__name__)


def _guard_production() -> None:
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Simulation endpoint disabled in production",
        )


@router.post("/payment-failure", summary="Inject a synthetic failed payment event")
async def simulate_payment_failure(
    req: SimulatePaymentRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_guard_production),
):
    """
    Creates a synthetic failed PaymentEvent and runs through the complete
    recovery pipeline (ingest → detect → diagnose → select strategy → evaluate policy).
    Simulated events instantly generate RecoveryOpportunities and PendingApprovals in DB.
    """
    from uuid import UUID, uuid4
    from decimal import Decimal
    from app.repositories.payment_event import PaymentEventRepository
    from app.schemas.payment_event import PaymentEventRead
    from app.schemas.customer import CustomerContext
    from app.schemas.policy import PolicyRead
    from app.schemas.agents import DetectionInput
    from app.services.detection import DetectionService
    from app.services.diagnosis import DiagnosisService
    from app.services.strategy import StrategyService
    from app.services.policy_gateway import PolicyGatewayService

    # 1. Ingest payment event into DB
    result = await PaymentEventService(db).ingest_simulated(req)
    payment_id = result.get("payment_id")

    if payment_id:
        payment_event_model = await PaymentEventRepository(db).get_by_payment_id(payment_id)
        if payment_event_model:
            payment_event_schema = PaymentEventRead.model_validate(payment_event_model)
            customer_context = CustomerContext(
                customer_id=UUID(str(payment_event_model.customer_id)),
                historical_payment_count=5,
                successful_payment_count=4,
                average_transaction_value=Decimal("15000.00"),
                risk_score=0.2,
            )
            merchant_policy = PolicyRead(
                policy_id=uuid4(),
                merchant_id=UUID(str(payment_event_model.merchant_id)),
                max_retry_count=2,
                max_discount_pct=Decimal("5.00"),
                allowed_channels=["RETRY", "PAYMENT_LINK", "REMINDER", "HUMAN_ESCALATION"],
                approval_threshold=Decimal("25000.00"),
                max_intervention_cost=Decimal("50.00"),
                active=True,
                version=1,
            )
            detection_input = DetectionInput(
                payment_event=payment_event_schema,
                customer_context=customer_context,
                merchant_policy=merchant_policy,
            )

            try:
                # 2. Run Detection Agent -> Create Opportunity
                det_output, opp, wf = await DetectionService(db).detect_and_create_opportunity(detection_input)
                if opp:
                    result["opportunity_id"] = str(opp.opportunity_id)
                    # 3. Run Diagnosis Agent
                    await DiagnosisService(db).diagnose_opportunity(opp.opportunity_id)
                    # 4. Run Strategy Engine
                    await StrategyService(db).select_strategy_for_opportunity(opp.opportunity_id)
                    # 5. Run Policy Gateway
                    clearance, updated_wf = await PolicyGatewayService(db).evaluate_opportunity_policy(opp.opportunity_id)
                    result["workflow_state"] = updated_wf.current_state

                    # If auto-approved (under threshold), run Action & Learning automatically
                    if clearance.approved and not clearance.requires_human_approval and clearance.clearance_token:
                        from app.services.action_agent import ActionService
                        from app.services.learning import LearningService

                        action_res, intervention, action_wf = await ActionService(db).execute_opportunity_intervention(
                            opp.opportunity_id, clearance.clearance_token
                        )
                        attrib_res, outcome, final_wf = await LearningService(db).record_opportunity_outcome(
                            opp.opportunity_id, payment_status="captured" if action_res.success else "failed"
                        )
                        result["workflow_state"] = final_wf.current_state
            except Exception as e:
                logger.error(f"message=Pipeline execution error during simulation | error={e}")
                result["pipeline_error"] = str(e)

    logger.info(f"message=Payment failure simulated & pipeline executed | payment_id={payment_id}")
    return result


@router.post("/batch", summary="Inject a batch of synthetic payment failures")
async def simulate_batch(
    count: int = 10,
    failure_code: str = "GATEWAY_ERROR",
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_guard_production),
):
    """
    Injects `count` synthetic payment failures with the given failure_code.
    Useful for populating data for dashboard testing.
    """
    from uuid import uuid4
    from decimal import Decimal
    from app.schemas.enums import PaymentMethod

    if count > 100:
        raise HTTPException(status_code=400, detail="Max batch size is 100")

    results = []
    svc = PaymentEventService(db)
    for _ in range(count):
        req = SimulatePaymentRequest(
            merchant_id=uuid4(),
            customer_id=uuid4(),
            amount=Decimal("999.00"),
            failure_code=failure_code,
            payment_method=PaymentMethod.CARD,
        )
        results.append(await svc.ingest_simulated(req))

    return {"injected": len(results), "failure_code": failure_code, "events": results}
