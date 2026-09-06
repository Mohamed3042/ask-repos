"""Runtime configuration. Every value is documented in `.env.example`."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings read from the environment (and a local `.env` when present)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- storage -------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://askrepos:askrepos@localhost:5433/askrepos",
        validation_alias="DATABASE_URL",
    )

    # --- ingestion -----------------------------------------------------------
    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    default_owner: str = Field(default="Mohamed3042", validation_alias="ASK_REPOS_OWNER")
    max_file_bytes: int = Field(default=200_000, validation_alias="ASK_REPOS_MAX_FILE_BYTES")

    # --- models (local, keyless) --------------------------------------------
    embed_model: str = Field(
        default="BAAI/bge-small-en-v1.5", validation_alias="ASK_REPOS_EMBED_MODEL"
    )
    embed_dim: int = Field(default=384, validation_alias="ASK_REPOS_EMBED_DIM")
    rerank_model: str = Field(
        default="Xenova/ms-marco-MiniLM-L-6-v2", validation_alias="ASK_REPOS_RERANK_MODEL"
    )
    rerank_enabled: bool = Field(default=True, validation_alias="ASK_REPOS_RERANK")
    model_cache_dir: str | None = Field(default=None, validation_alias="ASK_REPOS_MODEL_CACHE")

    # --- generation (optional) ----------------------------------------------
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.5-flash", validation_alias="GEMINI_MODEL")
    gemini_timeout_s: float = Field(default=60.0, validation_alias="GEMINI_TIMEOUT_S")

    # --- service -------------------------------------------------------------
    api_key: str | None = Field(default=None, validation_alias="ASK_REPOS_API_KEY")
    webhook_secret: str | None = Field(default=None, validation_alias="ASK_REPOS_WEBHOOK_SECRET")
    cors_origins: list[str] = Field(default_factory=list, validation_alias="ASK_REPOS_CORS_ORIGINS")
    otel_exporter: str = Field(default="none", validation_alias="ASK_REPOS_OTEL_EXPORTER")
    otel_endpoint: str | None = Field(default=None, validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Tests change the environment and need the next read to see it."""
    get_settings.cache_clear()
