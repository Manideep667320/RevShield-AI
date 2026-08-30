"""
Unit & Integration tests for Phase 7 — Recovery Metrics & KPI Aggregations.
Tests aggregate calculations for Recovery Rate %, Incremental Net Revenue, and Intervention ROI %.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.customer import Customer
from app.models.merchant import Merchant
from app.models.recovery import Intervention, RecoveryDecision, RecoveryOpportunity, RecoveryOutcome
from app.models.workflow import WorkflowState
from app.schemas.enums import OpportunityStatus, WorkflowStatus
from app.services.learning import LearningService


@pytest.mark.asyncio
async def test_get_recovery_summary_metrics(db):
    merchant = Merchant(merchant_id=uuid4(), name="Metrics Test Merchant")
    customer = Customer(customer_id=uuid4(), merchant_id=merchant.merchant_id)
    db.add_all([merchant, customer])
    await db.flush()

    # Opportunity 1: Recovered (2000.00)
    opp1 = RecoveryOpportunity(
        opportunity_id=uuid4(),
        payment_id=f"pay_{uuid4().hex[:12]}",
        recoverability_score=Decimal("0.80"),
        expected_revenue=Decimal("2000.00"),
        priority="HIGH",
        status=OpportunityStatus.RECOVERED.value,
    )
    dec1 = RecoveryDecision(
        decision_id=uuid4(),
        opportunity_id=opp1.opportunity_id,
        selected_action="PAYMENT_LINK",
        expected_value=Decimal("1500.00"),
    )
    int1 = Intervention(
        intervention_id=uuid4(),
        decision_id=dec1.decision_id,
        type="PAYMENT_LINK",
        status="CREATED",
        cost=Decimal("2.00"),
    )
    out1 = RecoveryOutcome(
        outcome_id=uuid4(),
        intervention_id=int1.intervention_id,
        payment_status="CAPTURED",
        recovered_amount=Decimal("2000.00"),
        incremental_recovery=Decimal("1900.00"),
        recorded_at=datetime.now(tz=timezone.utc),
    )

    # Opportunity 2: Failed (1000.00)
    opp2 = RecoveryOpportunity(
        opportunity_id=uuid4(),
        payment_id=f"pay_{uuid4().hex[:12]}",
        recoverability_score=Decimal("0.50"),
        expected_revenue=Decimal("1000.00"),
        priority="MEDIUM",
        status=OpportunityStatus.FAILED.value,
    )
    dec2 = RecoveryDecision(
        decision_id=uuid4(),
        opportunity_id=opp2.opportunity_id,
        selected_action="REMINDER",
        expected_value=Decimal("400.00"),
    )
    int2 = Intervention(
        intervention_id=uuid4(),
        decision_id=dec2.decision_id,
        type="REMINDER",
        status="SENT",
        cost=Decimal("0.50"),
    )

    db.add_all([opp1, dec1, int1, out1, opp2, dec2, int2])
    await db.commit()

    svc = LearningService(db)
    metrics = await svc.get_recovery_summary_metrics()

    assert metrics["total_opportunities"] == 2
    assert metrics["recovered_opportunities"] == 1
    assert metrics["recovery_rate_pct"] == 50.0
    assert Decimal(metrics["total_expected_revenue"]) == Decimal("3000.00")
    assert Decimal(metrics["total_recovered_amount"]) == Decimal("2000.00")
    assert Decimal(metrics["total_incremental_recovery"]) == Decimal("1900.00")
    assert Decimal(metrics["total_intervention_cost"]) == Decimal("2.50")
    # net_incremental = 1900.00 - 2.50 = 1897.50
    assert Decimal(metrics["net_incremental_revenue"]) == Decimal("1897.50")
    # roi_pct = 1897.50 / 2.50 * 100 = 75900.0%
    assert metrics["roi_pct"] == 75900.0
