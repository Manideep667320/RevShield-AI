"""
Attribution Rules Engine — Phase 7
Time-window based attribution and TREATMENT vs CONTROL baseline incrementality calculations.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pydantic import BaseModel
from app.core.logging import get_logger
from app.schemas.enums import ActionType, ExperimentGroup, FailureCause

logger = get_logger(__name__)

ATTRIBUTION_WINDOWS: dict[ActionType, timedelta] = {
    ActionType.RETRY: timedelta(hours=24),
    ActionType.PAYMENT_LINK: timedelta(hours=72),
    ActionType.REMINDER: timedelta(hours=48),
    ActionType.HUMAN_ESCALATION: timedelta(hours=120),
    ActionType.NO_ACTION: timedelta(hours=24),
}

BASELINE_ORGANIC_RATES: dict[FailureCause, float] = {
    FailureCause.TEMPORARY_FAILURE: 0.10,
    FailureCause.INSUFFICIENT_FUNDS: 0.05,
    FailureCause.PAYMENT_METHOD_FAILURE: 0.00,
    FailureCause.EXPIRED_PAYMENT: 0.00,
    FailureCause.CUSTOMER_ABANDONMENT: 0.02,
    FailureCause.RISK_REJECTION: 0.00,
    FailureCause.UNKNOWN: 0.05,
}


class AttributionResult(BaseModel):
    attributed: bool
    recovered_amount: Decimal
    incremental_recovery: Decimal
    time_to_recovery: timedelta | None
    experiment_group: ExperimentGroup
    reason: str


class AttributionEngine:
    """Calculates time-window attribution and incremental net recovery against baseline."""

    @staticmethod
    def evaluate_attribution(
        payment_status: str,
        amount: Decimal,
        executed_at: datetime | None,
        recorded_at: datetime,
        action_type: ActionType,
        cause: FailureCause = FailureCause.TEMPORARY_FAILURE,
        experiment_group: ExperimentGroup = ExperimentGroup.TREATMENT,
    ) -> AttributionResult:
        is_success = payment_status.lower() in {"captured", "success", "paid", "recovered"}

        if not is_success:
            return AttributionResult(
                attributed=False,
                recovered_amount=Decimal("0.00"),
                incremental_recovery=Decimal("0.00"),
                time_to_recovery=None,
                experiment_group=experiment_group,
                reason="Payment outcome is not successful",
            )

        time_to_recovery = None
        if executed_at:
            if executed_at.tzinfo is None:
                executed_at = executed_at.replace(tzinfo=timezone.utc)
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=timezone.utc)
            time_to_recovery = recorded_at - executed_at
            max_window = ATTRIBUTION_WINDOWS.get(action_type, timedelta(hours=24))
            if time_to_recovery > max_window:
                logger.info(
                    f"message=Attribution rejected | reason=outside_time_window "
                    f"| time_to_recovery={time_to_recovery} | max_window={max_window}"
                )
                return AttributionResult(
                    attributed=False,
                    recovered_amount=amount,
                    incremental_recovery=Decimal("0.00"),
                    time_to_recovery=time_to_recovery,
                    experiment_group=experiment_group,
                    reason=f"Recovery occurred outside attribution window ({max_window})",
                )

        recovered_amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if experiment_group == ExperimentGroup.CONTROL:
            # Control group measures baseline organic recovery -> incremental recovery = 0
            return AttributionResult(
                attributed=True,
                recovered_amount=recovered_amount,
                incremental_recovery=Decimal("0.00"),
                time_to_recovery=time_to_recovery,
                experiment_group=ExperimentGroup.CONTROL,
                reason="Control group baseline observation (0 incremental lift)",
            )

        # Treatment group -> Subtract organic baseline rate
        organic_rate = BASELINE_ORGANIC_RATES.get(cause, 0.05)
        organic_amount = (recovered_amount * Decimal(str(organic_rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        incremental = max(Decimal("0.00"), recovered_amount - organic_amount)

        logger.info(
            f"message=Attribution success | recovered=₹{recovered_amount} "
            f"| organic_baseline=₹{organic_amount} | incremental=₹{incremental}"
        )

        return AttributionResult(
            attributed=True,
            recovered_amount=recovered_amount,
            incremental_recovery=incremental,
            time_to_recovery=time_to_recovery,
            experiment_group=ExperimentGroup.TREATMENT,
            reason="Attributed to intervention (net incremental lift calculated)",
        )
