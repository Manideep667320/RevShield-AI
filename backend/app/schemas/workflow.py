from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from app.schemas.enums import WorkflowStatus


class WorkflowStateCreate(BaseModel):
    opportunity_id: UUID
    temporal_run_id: str | None = None
    current_state: WorkflowStatus = WorkflowStatus.PENDING
    timeout_at: datetime | None = None
    idempotency_key: str   # always = f"recovery-{payment_id}"


class WorkflowStateRead(WorkflowStateCreate):
    workflow_id: UUID
    state_entered_at: datetime
    retry_count: int
    audit_log: list[dict] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class WorkflowStateUpdate(BaseModel):
    current_state: WorkflowStatus
    temporal_run_id: str | None = None
    audit_entry: dict | None = None   # appended to audit_log[]
