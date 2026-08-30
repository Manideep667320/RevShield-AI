"""
Core application settings — loaded once from environment variables.
All modules import from here. No hardcoded values elsewhere.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_env: str = "development"
    app_secret_key: str = "change-me"
    log_level: str = "INFO"
    app_version: str = "0.1.0"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # Database
    database_url: str = "postgresql+asyncpg://recovery:recovery_secret@localhost:5432/revenue_recovery"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_stream_name: str = "payment_events"
    redis_stream_consumer_group: str = "rra_workers"

    # Temporal
    temporal_host: str = "localhost"
    temporal_port: int = 7233
    temporal_namespace: str = "default"
    temporal_task_queue: str = "recovery-engine"

    # Razorpay
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # LLM
    llm_provider: str = "disabled"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 5

    # Policy
    clearance_token_ttl_minutes: int = 30
    policy_signing_secret: str = "change-this"

    # Observability
    enable_metrics: bool = True
    metrics_port: int = 9090

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def temporal_address(self) -> str:
        return f"{self.temporal_host}:{self.temporal_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
