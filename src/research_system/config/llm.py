"""Provider-agnostic chat model factory with per-role fallback chains.

Agents never construct provider classes themselves; they ask the factory for a model
by *role* (`reasoning` or `worker`). See notebooks 01-02 for the experiments behind this.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from langgraph.errors import GraphBubbleUp
from pydantic import BaseModel, ValidationError

from research_system.config.settings import ModelSpec, Role, Settings
from research_system.utils.errors import AllModelsFailedError, is_quota_exhausted, is_retryable
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
            max_retries=settings.groq_max_retries,
            timeout=settings.llm_timeout_s,
            **extra,
        )
    raise ValueError(f"Unknown provider: {spec.provider}")


def structured_output_kwargs(spec: ModelSpec) -> dict[str, Any]:
    """Per-provider `with_structured_output` options.

    Groq's gpt-oss models sometimes call the schema tool by a different name (`researchPlan`
    for `ResearchPlan`), which Groq rejects with a 400 `tool_use_failed` (1 of 4 planner calls
    in a probe). Its native JSON-schema mode involves no tool names and passed every probe.
    """
    return {"method": "json_schema"} if spec.provider == "groq" else {}


def with_fallbacks(
    primary: Runnable[Any, Any], backups: list[Runnable[Any, Any]]
) -> Runnable[Any, Any]:
    """Try each runnable in order; like `Runnable.with_fallbacks`, but with a useful final error.

    LangChain's fallback wrapper re-raises the *first* error when every model fails. With
    Groq first, a retired model's 404 then hides an exhausted OpenRouter quota, so the run is
    misclassified. Here, if any failure is a quota or transient error, a combined
    `AllModelsFailedError` is raised so `is_quota_exhausted`/`is_retryable` see all of them.
    Otherwise the first error is re-raised as before (e.g. so invalid structured output can
    still be repaired by `invoke_structured`).
    """
    if not backups:
        return primary
    chain = [primary, *backups]

    def run(value: Any, config: RunnableConfig) -> Any:
        errors: list[Exception] = []
        for runnable in chain:
            try:
                return runnable.invoke(value, config)
            except GraphBubbleUp:  # interrupts and other graph control flow must pass through
                raise
            except Exception as e:
                errors.append(e)
        if any(is_quota_exhausted(e) or is_retryable(e) for e in errors):
            raise AllModelsFailedError(errors) from errors[-1]
        raise errors[0]

    return RunnableLambda(run, name="model_fallbacks")


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
        return with_fallbacks(primary, list(backups))

    def structured(
        self, schema: type[SchemaT], role: Role, temperature: float = 0.0
    ) -> Runnable[Any, Any]:
        """Structured-output runnable: schema applied per model, *then* chained as fallbacks.

        (Proxying `with_structured_output` through a fallback wrapper is fragile; see nb 02.)
        """
        primary, *backups = [
            make_chat_model(spec, self.settings, temperature).with_structured_output(
                schema, **structured_output_kwargs(spec)
            )
            for spec in self.settings.models_for(role)
        ]
        return with_fallbacks(primary, backups)

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
