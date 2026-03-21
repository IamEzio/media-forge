"""Application configuration using Pydantic settings.

This centralizes environment configuration so both the API and worker
processes share a single source of truth. Values can be overridden via
environment variables when running in Docker or other environments.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Using Pydantic's BaseSettings provides validation and convenient
    environment-based overrides without sprinkling os.getenv() calls
    across the codebase.
    """

    project_name: str = Field(default="media-forge")

    # Redis / Celery configuration
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    celery_broker_url: str = Field(
        default="redis://redis:6379/0", alias="CELERY_BROKER_URL"
    )
    celery_result_backend: str = Field(
        default="redis://redis:6379/1", alias="CELERY_RESULT_BACKEND"
    )

    # Shared data directory and subpaths
    data_dir: Path = Field(default=Path("/data"), alias="DATA_DIR")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def input_dir(self) -> Path:
        return self.data_dir / "input"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "output"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "temp"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    lru_cache ensures we don't repeatedly read environment variables or
    re-parse configuration. This effectively creates a lightweight
    singleton without global state mutation.
    """

    return Settings()


settings = get_settings()
