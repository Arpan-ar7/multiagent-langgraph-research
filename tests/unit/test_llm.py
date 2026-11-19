"""LLM factory: provider quirks and the bounded structured-output repair loop."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, SecretStr

from research_system.config.llm import LLMFactory, make_chat_model
from research_system.config.settings import ModelSpec, Settings


class Answer(BaseModel):
    value: int


def _settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, openrouter_api_key=SecretStr("test-key"), **kw)  # type: ignore[call-arg]


def test_openrouter_timeout_is_converted_to_milliseconds() -> None:
    """Regression for the nb 01 gotcha: ChatOpenRouter's timeout is in ms."""
    model = make_chat_model(
        ModelSpec(provider="openrouter", model="x/y:free"), _settings(llm_timeout_s=45)
    )
    assert model.request_timeout == 45_000  # type: ignore[attr-defined]


def _factory_with(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[Any], **kw: Any
) -> tuple[LLMFactory, list[list[BaseMessage]]]:
    """Factory whose structured runnable replays `outcomes` (exceptions are raised)."""
    seen: list[list[BaseMessage]] = []

    def fake(messages: list[BaseMessage]) -> Any:
        seen.append(list(messages))
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    factory = LLMFactory(_settings(**kw))
    monkeypatch.setattr(factory, "structured", lambda *a, **k: RunnableLambda(fake))
    return factory, seen


def test_invalid_output_is_repaired_with_error_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    factory, seen = _factory_with(
        monkeypatch, [OutputParserException("missing field value"), Answer(value=7)]
    )
    result = factory.invoke_structured(Answer, "reasoning", [HumanMessage("q")])
    assert result == Answer(value=7)
    assert len(seen) == 2
    assert "missing field value" in str(seen[1][-1].content)  # the model saw its own error


def test_repair_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    errors = [OutputParserException(f"bad {i}") for i in range(5)]
    factory, seen = _factory_with(monkeypatch, errors, structured_repair_attempts=2)
    with pytest.raises(OutputParserException):
        factory.invoke_structured(Answer, "reasoning", [HumanMessage("q")])
    assert len(seen) == 3  # 1 attempt + 2 repairs


def test_groq_structured_output_uses_json_schema_mode() -> None:
    """Regression: gpt-oss on Groq mis-cased the schema tool name (400 tool_use_failed)."""
    from research_system.config.llm import structured_output_kwargs

    assert structured_output_kwargs(ModelSpec(provider="groq", model="openai/gpt-oss-120b")) == {
        "method": "json_schema"
    }
    assert structured_output_kwargs(ModelSpec(provider="openrouter", model="x/y:free")) == {}


def test_groq_first_uses_current_groq_models() -> None:
    s = _settings(groq_api_key=SecretStr("gk"), groq_position="first")
    assert s.models_for("reasoning")[0] == ModelSpec(provider="groq", model="openai/gpt-oss-120b")
    assert s.models_for("worker")[0] == ModelSpec(provider="groq", model="openai/gpt-oss-20b")
    assert all(m.provider != "groq" for m in s.models_for("judge"))


def test_groq_uses_its_own_retry_budget() -> None:
    """Groq's per-minute token limits clear in seconds, so it retries more than other providers."""
    s = _settings(groq_api_key=SecretStr("gk"), llm_max_retries=1, groq_max_retries=4)
    groq = make_chat_model(ModelSpec(provider="groq", model="openai/gpt-oss-20b"), s)
    other = make_chat_model(ModelSpec(provider="openrouter", model="x/y:free"), s)
    assert groq.max_retries == 4  # type: ignore[attr-defined]
    assert other.max_retries == 1  # type: ignore[attr-defined]
