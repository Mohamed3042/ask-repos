"""Runtime configuration. Every value is documented in `.env.example`."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    # Pairs scored per forward pass. The score of a pair does not depend on its batch, so this
    # is purely a memory knob: MiniLM's attention on a batch of 64 padded to 512 tokens is
    # ~800 MB of activations, which killed the 512 MB hosted demo mid-answer (2026-09-06).
    rerank_batch_size: int = Field(default=8, validation_alias="ASK_REPOS_RERANK_BATCH")
    model_cache_dir: str | None = Field(default=None, validation_alias="ASK_REPOS_MODEL_CACHE")

    # --- generation (optional) ----------------------------------------------
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.5-flash", validation_alias="GEMINI_MODEL")
    gemini_timeout_s: float = Field(default=60.0, validation_alias="GEMINI_TIMEOUT_S")

    # --- service -------------------------------------------------------------
    api_key: str | None = Field(default=None, validation_alias="ASK_REPOS_API_KEY")
    webhook_secret: str | None = Field(default=None, validation_alias="ASK_REPOS_WEBHOOK_SECRET")
    # `NoDecode` keeps pydantic-settings from JSON-decoding this before the validator
    # below sees it. Without it an empty ASK_REPOS_CORS_ORIGINS - which is exactly what
    # Compose passes when the variable is unset - crashed the service at start-up.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list, validation_alias="ASK_REPOS_CORS_ORIGINS"
    )
    # --- hosted demo ---------------------------------------------------------
    # A read-only deployment answers and searches, and refuses everything that writes:
    # POST /v1/index, the push webhook, and approving an agent-requested re-index. The
    # interrupt itself still fires, because the approval gate is the thing worth showing.
    readonly: bool = Field(default=False, validation_alias="ASK_REPOS_READONLY")
    # Fixed-window requests per minute per client for the answer and search routes.
    # 0 disables the limiter (the default, for local and CI use).
    rate_limit_per_minute: int = Field(
        default=0, validation_alias="ASK_REPOS_RATE_LIMIT_PER_MINUTE"
    )
    # One sentence the UI shows in its demo banner, e.g. who the corpus belongs to.
    demo_note: str | None = Field(default=None, validation_alias="ASK_REPOS_DEMO_NOTE")

    otel_exporter: str = Field(default="none", validation_alias="ASK_REPOS_OTEL_EXPORTER")
    otel_endpoint: str | None = Field(default=None, validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT")

    @field_validator("demo_note", mode="before")
    @classmethod
    def _blank_is_absent(cls, value: object) -> object:
        # Compose passes "" for a variable nobody set. An empty banner note is not a note.
        if isinstance(value, str) and not value.strip():
            return None
        return value

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
