from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TracePilot API"
    app_env: str = "local"
    database_url: str = "postgresql+asyncpg://tracepilot:tracepilot@127.0.0.1:5432/tracepilot"
    redis_url: str = "redis://127.0.0.1:6379/0"
    cors_origins: list[str] = ["http://127.0.0.1:5173"]
    default_organization_id: str = "00000000-0000-0000-0000-000000000001"
    default_user_id: str = "00000000-0000-0000-0000-000000000101"
    default_project_id: str = "00000000-0000-0000-0000-000000000201"
    redis_execution_stream: str = "tracepilot:execution-jobs"
    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 50
    outbox_max_attempts: int = 10
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
