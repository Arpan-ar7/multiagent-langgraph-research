"""Shared graph state: the only channel through which agents communicate (notebook 05).

Keys written by parallel researchers use the `operator.add` reducer, so concurrent
updates are concatenated instead of conflicting.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from research_system.schemas import Critique, Draft, FactCheckReport, Finding, ResearchPlan


class ResearchState(TypedDict, total=False):
    query: str
    options: dict[str, Any]  # RunOptions.model_dump(); checkpointed with the run
    plan: ResearchPlan
    findings: Annotated[list[Finding], operator.add]
    failures: Annotated[list[str], operator.add]
    warnings: Annotated[list[str], operator.add]
    metrics: Annotated[list[dict[str, Any]], operator.add]
    fact_check: FactCheckReport
    draft: Draft
    critique: Critique
    iteration: int
    report: str


class ResearcherTask(TypedDict):
    """Private payload sent to each parallel researcher via `Send`."""

    sub_question: str
    strategy: str
    max_tool_calls: int
