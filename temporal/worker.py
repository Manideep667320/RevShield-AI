"""
Temporal Worker Bootstrap — Phase 0 skeleton.
Activities and workflows wired in Phase 4+.
"""
import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Activity and workflow registrations are imported per phase:
# Phase 2: detection activities
# Phase 3: diagnosis activities
# Phase 4: strategy, policy, action activities + RecoveryWorkflow
WORKFLOWS: list = []
ACTIVITIES: list = []


async def run_worker() -> None:
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=WORKFLOWS,
        activities=ACTIVITIES,
    )
    logger.info(f"message=Temporal worker started | task_queue={settings.temporal_task_queue}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
