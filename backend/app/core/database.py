import os
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from app.core.logging import get_logger
from app.models.base import Base

logger = get_logger(__name__)


def _create_engine_for_url(url: str):
    if "sqlite" in url:
        return create_async_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_async_engine(
        url,
        echo=not settings.is_production,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )


engine = _create_engine_for_url(settings.database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a scoped async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """Create all tables. If PostgreSQL is unreachable, fall back to SQLite."""
    global engine, AsyncSessionLocal

    # Import all models so Base.metadata is populated
    import app.models.recovery  # noqa
    import app.models.payment_event  # noqa
    import app.models.customer  # noqa
    import app.models.merchant  # noqa
    import app.models.policy  # noqa
    import app.models.workflow  # noqa
    import app.models.audit  # noqa

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("message=Database tables created on primary engine")
    except Exception as e:
        logger.warning(f"message=Primary database connection failed ({e}). Falling back to SQLite.")
        sqlite_url = "sqlite+aiosqlite:///./revenue_recovery.db"
        engine = _create_engine_for_url(sqlite_url)
        AsyncSessionLocal.configure(bind=engine)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("message=SQLite database tables created successfully")
