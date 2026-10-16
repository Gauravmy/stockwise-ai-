"""Application configuration loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "StockWise AI"
    environment: str = Field(default="development", alias="STOCKWISE_ENV")
    database_url: str = Field(
        default=f"sqlite:///{(BACKEND_DIR / 'stockwise.db').as_posix()}",
        alias="DATABASE_URL",
    )
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000", alias="CORS_ORIGINS"
    )
    # Optional regex for extra allowed origins, e.g. Vercel preview URLs:
    # https://stockwise-ai.*\.vercel\.app
    cors_origin_regex: str | None = Field(default=None, alias="CORS_ORIGIN_REGEX")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Upload safety limits
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, alias="MAX_UPLOAD_BYTES")
    max_upload_rows: int = Field(default=200_000, alias="MAX_UPLOAD_ROWS")

    # Run Alembic migrations automatically at startup (convenient for local use).
    auto_migrate: bool = Field(default=True, alias="AUTO_MIGRATE")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
