"""HTTP request/response models (kept separate from the agents' internal schemas)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from research_system.schemas import Critique, ResearchPlan
from research_system.service import RunSnapshot


class RunOptionsIn(BaseModel):
    """Optional per-run overrides; unset fields use server defaults."""

    max_sub_questions: int | None = Field(default=None, ge=1, le=5)
    max_tool_calls: int | None = Field(default=None, ge=1, le=10)
    max_iterations: int | None = Field(default=None, ge=1, le=4)
    approval_threshold: int | None = Field(default=None, ge=1, le=5)
    human_review: bool | None = None


class StartRunRequest(BaseModel):
    query: str = Field(min_length=5, max_length=500)
    options: RunOptionsIn = Field(default_factory=RunOptionsIn)


class ReviewRequest(BaseModel):
    """Sub-questions to keep (verbatim). Omit or leave empty to approve the plan as-is."""

    sub_questions: list[str] | None = None


class RunCreated(BaseModel):
    thread_id: str
    events_url: str


class StepTiming(BaseModel):
    node: str
    count: int
    seconds: float


class SourceView(BaseModel):
    """A cited source: its `[n]` number, rule-based credibility, and claims it supports."""

    n: int
    url: str
    domain: str
    credibility: float
    claims: int
    contested: int


class RunView(BaseModel):
    """Public view of a run."""

    thread_id: str
    status: str
    active: bool
    query: str | None = None
    plan: ResearchPlan | None = None
    critique: Critique | None = None
    report: str | None = None
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    timings: list[StepTiming] = Field(default_factory=list)
    sources: list[SourceView] = Field(default_factory=list)

    @classmethod
    def from_snapshot(cls, snap: RunSnapshot, active: bool, include_report: bool = True) -> RunView:
        totals: dict[str, list[float]] = {}
        for metric in snap.metrics:
            totals.setdefault(metric["node"], []).append(float(metric.get("seconds", 0.0)))
        timings = [
            StepTiming(node=node, count=len(values), seconds=round(sum(values), 2))
            for node, values in totals.items()
        ]
        return cls(
            thread_id=snap.thread_id,
            status=snap.status.value,
            active=active,
            query=snap.query,
            plan=snap.plan,
            critique=snap.critique,
            report=snap.report if include_report else None,
            failures=snap.failures,
            warnings=snap.warnings,
            timings=timings,
            sources=[SourceView.model_validate(s) for s in snap.sources],
        )


class RunSummary(BaseModel):
    thread_id: str
    status: str
    query: str | None


class Health(BaseModel):
    status: str = "ok"
    version: str
    providers: dict[str, Any]
    defaults: dict[str, Any] = Field(default_factory=dict)  # server's default run options
