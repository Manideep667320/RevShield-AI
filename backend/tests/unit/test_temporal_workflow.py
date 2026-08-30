"""
Unit tests for Temporal Workflow Activities & Pipeline orchestration.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.customer import Customer
from app.models.merchant import Merchant
from app.models.payment_event import PaymentEvent
from app.models.recovery import RecoveryOpportunity
from app.models.workflow import WorkflowState
from app.schemas.enums import FailureCause, WorkflowStatus
from app.workflows.activities import (
    detect_activity,
    diagnose_activity,
    select_strategy_activity,
    evaluate_policy_activity,
    execute_action_activity,
)


@pytest.mark.asyncio
async def test_temporal_activities_pipeline_sequence(db):
    # 1. Seed Merchant & Customer
    merchant = Merchant(
        merchant_id=uuid4(),
        name="Temporal Test Merchant",
        recovery_policy={
            "max_retry_count": 2,
            "approval_threshold": 25000,
            "allowed_channels": ["RETRY", "PAYMENT_LINK", "REMINDER"],
        },
    )
    customer = Customer(
        customer_id=uuid4(), merchant_id=merchant.merchant_id
    )
    db.add_all([merchant, customer])
    await db.commit()

    payment_id = f"pay_{uuid4().hex[:16]}"
    payment_event_dict = {
        "payment_id": payment_id,
        "merchant_id": str(merchant.merchant_id),
        "customer_id": str(customer.customer_id),
        "amount": "5000.00",
        "currency": "INR",
        "payment_method": "CARD",
        "failure_code": "GATEWAY_ERROR",
        "status": "failed",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    # 1. Activity: Detect
    det_res = await detect_activity(payment_event_dict, db=db)
    assert det_res["eligible"] is True
    assert det_res["opportunity_id"] is not None
    opp_id_str = det_res["opportunity_id"]

    # 2. Activity: Diagnose
    diag_res = await diagnose_activity(opp_id_str, db=db)
    assert diag_res["cause"] == FailureCause.TEMPORARY_FAILURE.value
    assert diag_res["workflow_state"] == WorkflowStatus.DIAGNOSING.value

    # 3. Activity: Select Strategy
    strat_res = await select_strategy_activity(opp_id_str, db=db)
    assert strat_res["selected_action"] == "RETRY"
    assert strat_res["workflow_state"] == WorkflowStatus.STRATEGY_SELECTED.value

    # 4. Activity: Evaluate Policy
    policy_res = await evaluate_policy_activity(opp_id_str, db=db)
    assert policy_res["approved"] is True
    assert policy_res["clearance_token"] != ""
    assert policy_res["workflow_state"] == WorkflowStatus.AWAITING_POLICY.value

    # 5. Activity: Execute Action
    action_res = await execute_action_activity(opp_id_str, policy_res["clearance_token"], db=db)
    assert action_res["success"] is True
    assert action_res["external_ref"] != ""
    assert action_res["workflow_state"] == WorkflowStatus.EXECUTING.value
