"""
Revenue Recovery Engine — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.api.v1 import api_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle hooks."""
    logger.info(f"message=Starting Revenue Recovery Engine | env={settings.app_env} | version={settings.app_version}")

    # Preload taxonomy into cache (fail fast if YAML is malformed)
    from app.services.taxonomy import load_taxonomy
    load_taxonomy()

    # Initialize DB tables (with SQLite fallback if Postgres is down)
    from app.core.database import create_tables
    try:
        await create_tables()
    except Exception as e:
        logger.error(f"message=DB initialization error | error={e}")

    # Ensure Redis consumer group exists
    from app.services.event_queue import get_publisher
    try:
        await get_publisher().ensure_consumer_group()
    except Exception as e:
        logger.error(f"message=Redis consumer group setup failed | error={e}")

    yield
    logger.info("message=Revenue Recovery Engine shutdown")


app = FastAPI(
    title="AI Revenue Recovery Engine",
    description="Autonomous engine that detects, diagnoses, and recovers failed payments.",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global Error Handlers ───────────────────────────────────────────────
@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    logger.error(f"message=AppError | status={exc.status_code} | detail={exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Catch-all: prevents raw tracebacks leaking to clients in production."""
    logger.exception(f"message=Unhandled exception | error={exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )

# ── Routes ─────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")

# ── Health Check & Root ───────────────────────────────────────────────────
@app.get("/", tags=["System"], summary="Root status check")
async def root():
    return {"status": "ok", "service": "RevShield AI Engine", "version": settings.app_version, "docs": "/docs"}


@app.get("/health", tags=["System"], summary="Service health check")
async def health():
    return {"status": "ok", "version": settings.app_version, "env": settings.app_env}
