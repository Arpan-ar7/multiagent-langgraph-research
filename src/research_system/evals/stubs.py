"""Deterministic stub agents and judge for `--dry-run` evaluations (no API calls).

Outputs vary per question (seeded by the question text) so summaries are non-trivial, and
every stub calls a fake chat model so usage counting is exercised too.
"""

from __future__ import annotations

import random
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from research_system.agents.base import Agents
from research_system.evals.metrics import JudgeScore
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
from research_system.utils.sources import credibility

_DOMAINS = ("arxiv.org", "example.com", "en.wikipedia.org", "news.example.net", "data.gov")


def _rng(*parts: Any) -> random.Random:
    return random.Random("|".join(map(str, parts)))


def _touch_llm() -> None:
    GenericFakeChatModel(messages=iter([AIMessage(content="ok")])).invoke("stub")


def dry_run_agents() -> Agents:
    def make_plan(query: str) -> ResearchPlan:
        _touch_llm()
        return ResearchPlan(
            objective=query,
            research_type="exploratory",
            report_outline=["Summary", "Findings", "Outlook"],
            sub_questions=[
                SubQuestion(
                    question=f"{query[:50]} (aspect {i})", rationale="stub", search_strategy="web"
                )
                for i in range(1, 6)
            ],
        )

    def research(sub_question: str, strategy: str = "web", *, max_tool_calls: int = 4) -> Finding:
        _touch_llm()
        rng = _rng(sub_question)
        urls = [f"https://{d}/{rng.randint(1, 999)}" for d in rng.sample(_DOMAINS, 2)]
        return Finding(
            sub_question=sub_question,
            summary="stub",
            confidence="medium",
            retrieved_urls=urls,
            claims=[
                Claim(statement=f"Fact {i} on {sub_question[:40]}", source_urls=[u])
                for i, u in enumerate(urls)
            ],
        )

    def fact_check(findings: list[Finding]) -> FactCheckReport:
        _touch_llm()
        claims = [
            VerifiedClaim(
                statement=c.statement,
                source_urls=c.source_urls,
                credibility=credibility(c.source_urls[0]),
                status=_rng(c.statement).choice(
                    ["supported", "supported", "supported", "contested", "unverified"]
                ),
            )
            for f in findings
            for c in f.claims
        ]
        return FactCheckReport(claims=claims)

    def write(plan: ResearchPlan, fact_check: FactCheckReport) -> Draft:
        _touch_llm()
        numbers = number_sources(fact_check)
        body = " ".join(
            f"{c.statement} [{numbers[c.source_urls[0]]}]." for c in fact_check.usable_claims()
        )
        return Draft(markdown=f"# {plan.objective}\n\n{body}", sources=numbers)

    def critique(plan: ResearchPlan, report: str) -> Critique:
        # Stateless on purpose: decide from the report itself, so runs never influence each other.
        # Reports that already contain follow-up research pass; otherwise ~60% ask for more.
        _touch_llm()
        has_follow_up = "follow-up" in report
        score = 4 if has_follow_up or _rng(plan.objective).random() >= 0.6 else 3
        return Critique(
            coverage=score,
            evidence_use=4,
            coherence=4,
            justification="stub",
            follow_up_questions=[] if score >= 4 else [f"{plan.objective[:40]} follow-up"],
        )

    return Agents(
        plan=make_plan, research=research, fact_check=fact_check, write=write, critique=critique
    )


def dry_run_judge(question: str, report: str) -> JudgeScore:
    rng = _rng(question, len(report))
    bonus = 1 if len(report) > 900 else 0  # longer (looped) reports score a bit higher
    return JudgeScore(
        relevance=rng.randint(3, 4) + bonus,
        completeness=min(5, rng.randint(2, 4) + bonus),
        specificity=rng.randint(2, 4),
        rationale="dry-run stub score",
    )
