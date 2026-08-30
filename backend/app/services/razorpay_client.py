"""
Razorpay Sandbox Integration Client — Phase 6
Handles sandbox API communications for retries, payment link generation, reminders, and human escalation tickets.
Integrates with CircuitBreaker to protect against downstream failures.
"""
from decimal import Decimal
from uuid import UUID, uuid4
from pydantic import BaseModel
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.enums import ActionType
from app.services.circuit_breaker import razorpay_circuit_breaker

logger = get_logger(__name__)


class RazorpayResult(BaseModel):
    success: bool
    external_ref: str
    status: str
    message: str
    action_type: ActionType


class RazorpaySandboxClient:
    """Razorpay API client (Sandbox simulator in dev/staging)."""

    def __init__(self, simulate_failure: bool = False):
        self.simulate_failure = simulate_failure

    def _execute(self, action: ActionType, call_fn) -> RazorpayResult:
        razorpay_circuit_breaker.check_state()
        if self.simulate_failure:
            razorpay_circuit_breaker.record_failure()
            logger.error(f"message=Razorpay API call failed (simulated) | action={action.value}")
            return RazorpayResult(
                success=False,
                external_ref=f"err_{uuid4().hex[:12]}",
                status="FAILED",
                message="Razorpay gateway timeout / error",
                action_type=action,
            )
        try:
            res = call_fn()
            razorpay_circuit_breaker.record_success()
            logger.info(f"message=Razorpay API call succeeded | action={action.value} | ref={res.external_ref}")
            return res
        except Exception as e:
            razorpay_circuit_breaker.record_failure()
            raise e

    def retry_payment(self, payment_id: str) -> RazorpayResult:
        def _call():
            ref = f"pay_retry_{uuid4().hex[:12]}"
            return RazorpayResult(
                success=True,
                external_ref=ref,
                status="CAPTURED",
                message=f"Automated retry executed for payment {payment_id}",
                action_type=ActionType.RETRY,
            )
        return self._execute(ActionType.RETRY, _call)

    def create_payment_link(self, amount: Decimal, customer_email: str = "", customer_phone: str = "") -> RazorpayResult:
        def _call():
            ref = f"plink_{uuid4().hex[:12]}"
            return RazorpayResult(
                success=True,
                external_ref=ref,
                status="CREATED",
                message=f"Payment link created for ₹{amount} (link=https://rzp.io/l/{ref})",
                action_type=ActionType.PAYMENT_LINK,
            )
        return self._execute(ActionType.PAYMENT_LINK, _call)

    def send_reminder(self, customer_phone: str = "", payment_link: str = "") -> RazorpayResult:
        def _call():
            ref = f"sms_{uuid4().hex[:12]}"
            return RazorpayResult(
                success=True,
                external_ref=ref,
                status="SENT",
                message=f"Payment reminder SMS dispatched to {customer_phone}",
                action_type=ActionType.REMINDER,
            )
        return self._execute(ActionType.REMINDER, _call)

    def escalate_to_human(self, opportunity_id: UUID, reasoning: str = "") -> RazorpayResult:
        def _call():
            ref = f"ticket_{uuid4().hex[:12]}"
            return RazorpayResult(
                success=True,
                external_ref=ref,
                status="ESCALATED",
                message=f"Human escalation ticket {ref} created for opportunity {opportunity_id}",
                action_type=ActionType.HUMAN_ESCALATION,
            )
        return self._execute(ActionType.HUMAN_ESCALATION, _call)
