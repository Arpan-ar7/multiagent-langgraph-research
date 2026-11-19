"""Fallback chains surface every failure (regression: Groq 404 masking an OpenRouter quota)."""

from __future__ import annotations

from typing import Any, NoReturn

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.errors import GraphInterrupt
from pydantic import BaseModel, ValidationError

from research_system.config.llm import with_fallbacks
from research_system.utils.errors import AllModelsFailedError, is_quota_exhausted, is_retryable


class HTTPError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def failing(exc: Exception) -> RunnableLambda[Any, Any]:
    def run(_: Any) -> NoReturn:
        raise exc

    return RunnableLambda(run)


NOT_FOUND = HTTPError("The model `llama-3.3-70b-versatile` does not exist", 404)
QUOTA = HTTPError("Rate limit exceeded: free-models-per-day", 429)
RATE_LIMIT = HTTPError("Rate limit exceeded: 20 requests per minute", 429)


def test_backup_answers_when_primary_fails() -> None:
    chain = with_fallbacks(failing(NOT_FOUND), [RunnableLambda(lambda x: f"ok:{x}")])
    assert chain.invoke("q") == "ok:q"


def test_quota_behind_a_404_is_not_masked() -> None:
    chain = with_fallbacks(failing(NOT_FOUND), [failing(QUOTA)])
    with pytest.raises(AllModelsFailedError) as info:
        chain.invoke("q")
    assert info.value.errors == [NOT_FOUND, QUOTA]
    assert is_quota_exhausted(info.value) and not is_retryable(info.value)


def test_transient_failure_behind_a_404_stays_retryable() -> None:
    chain = with_fallbacks(failing(NOT_FOUND), [failing(RATE_LIMIT)])
    with pytest.raises(AllModelsFailedError) as info:
        chain.invoke("q")
    assert is_retryable(info.value) and not is_quota_exhausted(info.value)


def test_validation_errors_are_reraised_unchanged_for_repair() -> None:
    class Plan(BaseModel):
        n: int

    try:
        Plan.model_validate({"n": "x"})
    except ValidationError as e:
        invalid = e
    chain = with_fallbacks(failing(invalid), [failing(NOT_FOUND)])
    with pytest.raises(ValidationError):
        chain.invoke("q")


def test_graph_interrupts_pass_through_without_fallback() -> None:
    called: list[str] = []
    backup = RunnableLambda(lambda x: called.append(x))
    with pytest.raises(GraphInterrupt):
        with_fallbacks(failing(GraphInterrupt()), [backup]).invoke("q")
    assert called == []


def test_single_model_is_returned_as_is() -> None:
    model = RunnableLambda(lambda x: x)
    assert with_fallbacks(model, []) is model
