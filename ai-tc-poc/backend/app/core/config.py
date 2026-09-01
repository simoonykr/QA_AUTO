from functools import lru_cache
from decimal import Decimal
from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TracePilot API"
    app_env: str = "local"
    database_url: str = "postgresql+asyncpg://tracepilot:tracepilot@127.0.0.1:5432/tracepilot"
    redis_url: str = "redis://127.0.0.1:6379/0"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://127.0.0.1:5174"]
    default_organization_id: str = "00000000-0000-0000-0000-000000000001"
    default_user_id: str = "00000000-0000-0000-0000-000000000101"
    default_project_id: str = "00000000-0000-0000-0000-000000000201"
    redis_execution_stream: str = "tracepilot:execution-jobs"
    redis_worker_group: str = "tracepilot-workers"
    redis_worker_consumer: str = "playwright-worker-1"
    worker_poll_block_ms: int = 5000
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "tracepilot"
    minio_secret_key: str = "tracepilot-local-only"
    minio_secure: bool = False
    minio_artifact_bucket: str = "tracepilot-artifacts"
    demo_auth_enabled: bool = False
    demo_auth_username: str = ""
    demo_auth_password: str = ""
    demo_session_secret: str = ""
    demo_session_ttl_hours: int = 8
    demo_cookie_secure: bool = False
    demo_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    demo_cookie_domain: str | None = None
    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 50
    outbox_max_attempts: int = 10
    openai_api_key: SecretStr | None = None
    ai_enabled: bool = False
    ai_max_calls_per_run: int = Field(default=0, ge=0, le=50)
    ai_daily_budget_usd: Decimal = Field(default=Decimal("0"), ge=0)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def ai_ready(self) -> bool:
        key = self.openai_api_key.get_secret_value().strip() if self.openai_api_key else ""
        return bool(
            self.ai_enabled
            and key
            and self.ai_max_calls_per_run > 0
            and self.ai_daily_budget_usd > 0
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
