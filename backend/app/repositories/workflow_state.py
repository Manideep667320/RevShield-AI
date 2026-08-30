"""
Workflow State Repository — DB access for WorkflowState entities.
Enforces unique constraint on idempotency_key ("recovery-{payment_id}").
"""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.models.workflow import WorkflowState
from app.repositories.base import BaseRepository
from app.schemas.enums import WorkflowStatus


class WorkflowStateRepository(BaseRepository[WorkflowState]):
    model = WorkflowState

    async def get_by_idempotency_key(self, idempotency_key: str) -> WorkflowState | None:
        result = await self.db.execute(
            select(WorkflowState).where(WorkflowState.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def get_by_opportunity_id(self, opportunity_id: UUID | str) -> WorkflowState | None:
        opp_str = str(opportunity_id)
        result = await self.db.execute(
            select(WorkflowState).where(
                (WorkflowState.opportunity_id == opp_str) | (WorkflowState.opportunity_id == UUID(opp_str))
            )
        )
        return result.scalars().first()

    async def create_idempotent(self, workflow: WorkflowState) -> tuple[WorkflowState, bool]:
        existing = await self.get_by_idempotency_key(workflow.idempotency_key)
        if existing:
            return existing, False
        try:
            created = await self.create(workflow)
            return created, True
        except IntegrityError:
            await self.db.rollback()
            existing = await self.get_by_idempotency_key(workflow.idempotency_key)
            return existing, False

    async def update_state(
        self,
        workflow_id: UUID,
        new_state: WorkflowStatus,
        *,
        temporal_run_id: str | None = None,
        audit_entry: dict | None = None,
    ) -> WorkflowState:
        wf = await self.get_or_raise(workflow_id)
        wf.current_state = new_state.value if isinstance(new_state, WorkflowStatus) else str(new_state)
        wf.state_entered_at = datetime.now(tz=timezone.utc)
        if temporal_run_id:
            wf.temporal_run_id = temporal_run_id
        if audit_entry:
            # Append entry to JSON list
            wf.audit_log = list(wf.audit_log or []) + [audit_entry]
        await self.db.flush()
        await self.db.refresh(wf)
        return wf
