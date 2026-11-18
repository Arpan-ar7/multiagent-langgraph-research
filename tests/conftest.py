"""Shared fixtures: deterministic stub agents (no LLM or network calls)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from research_system.agents.base import Agents
from research_system.config.settings import Settings
from research_system.schemas import (
    Claim,
    Critique,
    Draft,
    FactCheckReport,
    Finding,
    ResearchPlan,
    SubQuestion,
    VerifiedClaim,
)
from research_system.utils.citations import number_sources


def make_plan(questions: tuple[str, ...] = ("costs", "adoption", "risks")) -> ResearchPlan:
    return ResearchPlan(
        objective="Study widgets",
        research_type="exploratory",
        report_outline=["Summary", "Findings", "Outlook"],
        sub_questions=[
            SubQuestion(question=q, rationale="r", search_strategy="web") for q in questions
        ],
    )


def make_finding(question: str) -> Finding:
    url = f"https://example.org/{question.replace(' ', '-')}"
    return Finding(
        sub_question=question,
        summary=f"About {question}",
        confidence="medium",
        claims=[Claim(statement=f"Fact about {question}.", source_urls=[url])],
        retrieved_urls=[url],
    )


GOOD = Critique(coverage=5, evidence_use=5, coherence=5, justification="good")
WEAK = Critique(
    coverage=2,
    evidence_use=3,
    coherence=4,
    justification="missing pricing",
    follow_up_questions=["pricing"],
)


@dataclass
class StubAgents:
    """Configurable stub agents that record how often each one is called."""

    questions: tuple[str, ...] = ("costs", "adoption", "risks")
    failing_questions: set[str] = field(default_factory=set)
    fact_check_error: Exception | None = None
    writer_errors: list[Exception] = field(default_factory=list)  # raised once each, in order
    critiques: list[Critique] = field(default_factory=lambda: [GOOD])
    calls: Counter[str] = field(default_factory=Counter)
    researched: list[str] = field(default_factory=list)
    tool_limits: list[int] = field(default_factory=list)

    def plan(self, query: str) -> ResearchPlan:
        self.calls["plan"] += 1
        return make_plan(self.questions)

    def research(
        self, sub_question: str, strategy: str = "web", *, max_tool_calls: int = 4
    ) -> Finding:
        self.calls["research"] += 1
        self.researched.append(sub_question)
        self.tool_limits.append(max_tool_calls)
        if sub_question in self.failing_questions:
            raise ConnectionError("search provider down")
        return make_finding(sub_question)

    def fact_check(self, findings: list[Finding]) -> FactCheckReport:
        self.calls["fact_check"] += 1
        if self.fact_check_error:
            raise self.fact_check_error
        claims = [
            VerifiedClaim(
                statement=c.statement,
                source_urls=c.source_urls,
                status="supported",
                credibility=0.5,
            )
            for f in findings
            for c in f.claims
        ]
        return FactCheckReport(claims=claims)

    def write(self, plan: ResearchPlan, fact_check: FactCheckReport) -> Draft:
        self.calls["write"] += 1
        if self.writer_errors:
            raise self.writer_errors.pop(0)
        numbers = number_sources(fact_check)
        body = " ".join(
            f"{c.statement} [{numbers[c.source_urls[0]]}]" for c in fact_check.usable_claims()
        )
        return Draft(markdown=f"# Report\n\n{body}", sources=numbers)

    def critique(self, plan: ResearchPlan, report: str) -> Critique:
        self.calls["critique"] += 1
        return self.critiques.pop(0) if len(self.critiques) > 1 else self.critiques[0]

    def agents(self) -> Agents:
        return Agents(
            plan=self.plan,
            research=self.research,
            fact_check=self.fact_check,
            write=self.write,
            critique=self.critique,
        )


@pytest.fixture
def stubs() -> StubAgents:
    return StubAgents()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings isolated from the developer's .env and real data directories."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=tmp_path,
        reports_dir=tmp_path / "reports",
        checkpoint_db=tmp_path / "checkpoints.sqlite",
        max_sub_questions=5,
        max_iterations=2,
    )
