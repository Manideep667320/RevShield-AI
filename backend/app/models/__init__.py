"""
ORM model registry — import this to ensure all models are registered with Base.
Used by Alembic's env.py and the test database setup.
"""
from app.models.base import Base
from app.models.merchant import Merchant
from app.models.customer import Customer
from app.models.payment_event import PaymentEvent
from app.models.recovery import RecoveryOpportunity, RecoveryDecision, Intervention, RecoveryOutcome
from app.models.workflow import WorkflowState
from app.models.policy import Policy
from app.models.audit import AuditLog

__all__ = [
    "Base", "Merchant", "Customer", "PaymentEvent",
    "RecoveryOpportunity", "RecoveryDecision", "Intervention", "RecoveryOutcome",
    "WorkflowState", "Policy", "AuditLog",
]
