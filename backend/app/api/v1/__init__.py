from fastapi import APIRouter
from app.api.v1 import webhooks, opportunities, metrics, audit, approvals, merchants, simulate

api_router = APIRouter()

# Registry pattern — add new routers here, not in main.py
_routers = [
    webhooks.router,
    opportunities.router,
    metrics.router,
    audit.router,
    approvals.router,
    merchants.router,
    simulate.router,
]

for router in _routers:
    api_router.include_router(router)
