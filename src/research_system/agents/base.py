"""Agent interfaces and the dependency container handed to the graph.

The graph only depends on these call signatures, never on concrete LLM code, so tests can
inject deterministic stubs (notebook 07 §6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from research_system.schemas import Critique, Draft, FactCheckReport, Finding, ResearchPlan


def today() -> str:
    """Current date (ISO), injected into every prompt."""
    return date.today().isoformat()


class PlanFn(Protocol):
    def __call__(self, query: str) -> ResearchPlan: ...


class ResearchFn(Protocol):
    def __call__(
        self, sub_question: str, strategy: str = "web", *, max_tool_calls: int = 4
    ) -> Finding: ...


class FactCheckFn(Protocol):
    def __call__(self, findings: list[Finding]) -> FactCheckReport: ...


class WriteFn(Protocol):
    def __call__(self, plan: ResearchPlan, fact_check: FactCheckReport) -> Draft: ...


class CritiqueFn(Protocol):
    def __call__(self, plan: ResearchPlan, report: str) -> Critique: ...


@dataclass(frozen=True)
class Agents:
    """Every agent the research graph needs."""

    plan: PlanFn
    research: ResearchFn
    fact_check: FactCheckFn
    write: WriteFn
    critique: CritiqueFn
