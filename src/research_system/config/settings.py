"""Typed application settings, loaded from environment variables and `.env`.

Every tunable value lives here so behaviour changes are configuration, not code edits.
Environment variables use the `RS_` prefix (e.g. `RS_MAX_SUB_QUESTIONS=4`); API keys use
their conventional names (`OPENROUTER_API_KEY`, ...).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]

Provider = Literal["openrouter", "groq"]
Role = Literal["reasoning", "worker"]


class ModelSpec(BaseModel):
    """One model in a role's fallback chain."""

    provider: Provider
    model: str

    @classmethod
    def parse(cls, value: str) -> ModelSpec:
        """Parse `provider:model` (e.g. `openrouter:baidu/ernie-5.5-flash-preview:free`)."""
        provider, _, model = value.partition(":")
        return cls(provider=provider, model=model)


# Defaults decided in notebook 01 (see docs/experiments-log.md).
_NEMOTRON = "openrouter:nvidia/nemotron-3.5-super-vl:free"
_ERNIE = "openrouter:baidu/ernie-5.5-flash-preview:free"
_LING = "openrouter:inclusionai/ling-3.2-flash:free"


class Settings(BaseSettings):
    """Application configuration. Instantiate via `get_settings()`."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="RS_",
        extra="ignore",
        populate_by_name=True,
    )

    # --- API keys (conventional env names, no prefix) -------------------------------
    openrouter_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("OPENROUTER_API_KEY")
    )
    groq_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("GROQ_API_KEY")
    )
    tavily_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("TAVILY_API_KEY")
    )

    # --- Models: ordered fallback chains per role ------------------------------------
    reasoning_models: list[ModelSpec] = Field(
        default_factory=lambda: [ModelSpec.parse(m) for m in (_NEMOTRON, _ERNIE, _LING)]
    )
    worker_models: list[ModelSpec] = Field(
        default_factory=lambda: [ModelSpec.parse(m) for m in (_ERNIE, _NEMOTRON, _LING)]
    )
    groq_reasoning_model: str = "llama-3.3-70b-versatile"
    groq_worker_model: str = "llama-3.1-8b-instant"
    llm_timeout_s: float = 90.0
    llm_max_retries: int = 1  # low on purpose: fail fast and let the fallback chain take over
    writer_temperature: float = 0.3

    # --- Research behaviour (defaults; overridable per run) --------------------------
    max_sub_questions: int = Field(default=4, ge=1, le=5)
    max_tool_calls: int = Field(default=4, ge=1, le=10)
    max_model_calls: int = Field(default=7, ge=2, le=15)
    max_iterations: int = Field(default=2, ge=1, le=4)
    approval_threshold: int = Field(default=4, ge=1, le=5)
    human_review: bool = False
    structured_repair_attempts: int = Field(default=2, ge=0, le=3)

    # --- Tools ---------------------------------------------------------------------
    search_max_results: int = 5
    page_max_chars: int = 4000
    snippet_max_chars: int = 600

    # --- Paths -------------------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / "data"
    reports_dir: Path = PROJECT_ROOT / "reports"
    checkpoint_db: Path = PROJECT_ROOT / "data" / "checkpoints.sqlite"

    log_level: str = "INFO"

    @field_validator("reasoning_models", "worker_models", mode="before")
    @classmethod
    def _parse_model_list(cls, value: object) -> object:
        """Accept a comma-separated `provider:model` string from the environment."""
        if isinstance(value, str):
            return [ModelSpec.parse(v.strip()) for v in value.split(",") if v.strip()]
        return value

    def models_for(self, role: Role) -> list[ModelSpec]:
        """Fallback chain for a role. Groq goes first automatically when its key is set."""
        chain = list(self.reasoning_models if role == "reasoning" else self.worker_models)
        if self.groq_api_key:
            groq = self.groq_reasoning_model if role == "reasoning" else self.groq_worker_model
            chain.insert(0, ModelSpec(provider="groq", model=groq))
        return chain


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton.

    Also exports `.env` into `os.environ` (without overriding real env vars), because some
    libraries read their configuration from the environment directly (LangSmith tracing,
    Tavily, provider SDK defaults).
    """
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return Settings()
