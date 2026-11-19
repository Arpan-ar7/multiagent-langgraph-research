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
Role = Literal["reasoning", "worker", "judge"]


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
    # The evaluation judge deliberately starts with a model that is neither the writer nor the
    # critic, to reduce self-preference bias (see notebook 08).
    judge_models: list[ModelSpec] = Field(
        default_factory=lambda: [ModelSpec.parse(m) for m in (_LING, _NEMOTRON)]
    )
    # Llama 3.x was retired from Groq (404 model_not_found, 2026-11); both gpt-oss models pass
    # structured-output and tool-calling probes there.
    groq_reasoning_model: str = "openai/gpt-oss-120b"
    groq_worker_model: str = "openai/gpt-oss-20b"
    # Where Groq joins each chain when GROQ_API_KEY is set. "last" (default): a rescue model
    # after OpenRouter, because Groq's free tier allows only 8k tokens/minute, too little for
    # parallel researchers. "first": primary model (sensible on a paid Groq tier).
    groq_position: Literal["first", "last"] = "last"
    llm_timeout_s: float = 90.0
    llm_max_retries: int = 1  # low on purpose: fail fast and let the fallback chain take over
    # Groq's free tier has small per-minute token limits (8k TPM on gpt-oss-20b), so parallel
    # researchers hit 429s that clear within seconds. Its SDK honours `retry-after`, so a few
    # retries wait those out instead of failing over to a (possibly exhausted) fallback.
    groq_max_retries: int = Field(default=4, ge=0, le=10)
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

    @field_validator("reasoning_models", "worker_models", "judge_models", mode="before")
    @classmethod
    def _parse_model_list(cls, value: object) -> object:
        """Accept a comma-separated `provider:model` string from the environment."""
        if isinstance(value, str):
            return [ModelSpec.parse(v.strip()) for v in value.split(",") if v.strip()]
        return value

    def models_for(self, role: Role) -> list[ModelSpec]:
        """Fallback chain for a role. Groq joins it (see `groq_position`) when its key is set.

        The judge chain is left untouched so evaluation stays independent of the system's models.
        """
        if role == "judge":
            return list(self.judge_models)
        chain = list(self.reasoning_models if role == "reasoning" else self.worker_models)
        if self.groq_api_key:
            groq = self.groq_reasoning_model if role == "reasoning" else self.groq_worker_model
            spec = ModelSpec(provider="groq", model=groq)
            chain.insert(0 if self.groq_position == "first" else len(chain), spec)
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
