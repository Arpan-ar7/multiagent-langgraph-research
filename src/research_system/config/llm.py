"""Provider-agnostic chat model factory with per-role fallback chains.

Agents never construct provider classes themselves; they ask the factory for a model
by *role* (`reasoning` or `worker`). See notebooks 01-02 for the experiments behind this.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ValidationError

from research_system.config.settings import ModelSpec, Role, Settings
from research_system.utils.logging import get_logger

log = get_logger(__name__)
SchemaT = TypeVar("SchemaT", bound=BaseModel)


def make_chat_model(spec: ModelSpec, settings: Settings, temperature: float = 0.0) -> BaseChatModel:
    """Instantiate one chat model. `settings.llm_timeout_s` is always in seconds."""
    if spec.provider == "openrouter":
        from langchain_openrouter import ChatOpenRouter

        extra: dict[str, Any] = {}
        if settings.openrouter_api_key:  # else the client falls back to OPENROUTER_API_KEY
            extra["api_key"] = settings.openrouter_api_key.get_secret_value()
        return ChatOpenRouter(
            model=spec.model,
            temperature=temperature,
            max_retries=settings.llm_max_retries,
            timeout=int(settings.llm_timeout_s * 1000),  # ChatOpenRouter expects milliseconds
            **extra,
        )
    if spec.provider == "groq":
        from langchain_groq import ChatGroq

        extra = {}
        if settings.groq_api_key:
            extra["api_key"] = settings.groq_api_key.get_secret_value()
        return ChatGroq(
            model=spec.model,
            temperature=temperature,
            max_retries=settings.llm_max_retries,
            timeout=settings.llm_timeout_s,
            **extra,
        )
    raise ValueError(f"Unknown provider: {spec.provider}")


class LLMFactory:
    """Builds role-based runnables (plain or structured) with model fallbacks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def models(self, role: Role, temperature: float = 0.0) -> list[BaseChatModel]:
        """All models for a role, primary first."""
        return [
            make_chat_model(s, self.settings, temperature) for s in self.settings.models_for(role)
        ]

    def chat(self, role: Role, temperature: float = 0.0) -> Runnable[Any, BaseMessage]:
        """Plain chat runnable with fallbacks."""
        primary, *backups = self.models(role, temperature)
        return primary.with_fallbacks(backups) if backups else primary

    def structured(
        self, schema: type[SchemaT], role: Role, temperature: float = 0.0
    ) -> Runnable[Any, Any]:
        """Structured-output runnable: schema applied per model, *then* chained as fallbacks.

        (Proxying `with_structured_output` through a fallback wrapper is fragile; see nb 02.)
        """
        primary, *backups = [
            m.with_structured_output(schema) for m in self.models(role, temperature)
        ]
        return primary.with_fallbacks(backups) if backups else primary

    def invoke_structured(
        self,
        schema: type[SchemaT],
        role: Role,
        messages: list[BaseMessage],
        temperature: float = 0.0,
    ) -> SchemaT:
        """Invoke with bounded repair: on invalid output, show the model its error and retry."""
        runnable = self.structured(schema, role, temperature)
        history = list(messages)
        attempts = self.settings.structured_repair_attempts
        for attempt in range(attempts + 1):
            try:
                return cast(SchemaT, runnable.invoke(history))
            except (ValidationError, OutputParserException) as err:
                if attempt == attempts:
                    raise
                log.warning(
                    "structured_output_invalid", schema=schema.__name__, attempt=attempt + 1
                )
                history.append(
                    HumanMessage(
                        f"Your previous answer did not match the required schema:\n{err}\n"
                        "Return a corrected answer that satisfies the schema."
                    )
                )
        raise AssertionError("unreachable")
