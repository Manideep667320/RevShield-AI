from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class AuditLogCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    entity_type: str
    entity_id: UUID
    actor: str              # e.g. "detection_agent:v1.0"
    action: str             # e.g. "OPPORTUNITY_CREATED"
    input_snapshot: dict
    output_snapshot: dict
    model_version: str | None = None
    confidence: float | None = None
    policy_applied: dict | None = None


class AuditLogRead(AuditLogCreate):
    audit_id: UUID
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
