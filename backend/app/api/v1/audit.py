from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas import AuditLogRead

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("", response_model=list[AuditLogRead], summary="Paginated audit log")
async def list_audit_logs(
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    actor: str | None = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns immutable audit trail of all financial actions.
    Supports filtering by entity, actor, and time range.
    100% coverage required — every financial action must appear here.
    """
    # Phase 6: repository query wired here
    return []
