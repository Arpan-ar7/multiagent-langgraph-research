"""Fact-checker agent (notebook 06).

Deterministic checks first (citation grounding, source credibility), then one structured
LLM call to find contradictions between claims gathered by different researchers.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import HumanMessage

from research_system.config.llm import LLMFactory
from research_system.prompts import FACT_CHECK_PROMPT
from research_system.schemas import ConflictReport, FactCheckReport, Finding, VerifiedClaim
from research_system.schemas.review import ClaimStatus
from research_system.utils.sources import credibility


@dataclass(frozen=True)
class _CheckedClaim:
    statement: str
    source_urls: list[str]
    grounded: bool
    credibility: float


def ground_claims(findings: list[Finding]) -> list[_CheckedClaim]:
    """A claim is grounded only if every cited URL was actually retrieved by its researcher."""
    return [
        _CheckedClaim(
            statement=c.statement,
            source_urls=c.source_urls,
            grounded=all(u in f.retrieved_urls for u in c.source_urls),
            credibility=max(credibility(u) for u in c.source_urls),
        )
        for f in findings
        for c in f.claims
    ]


def build_report(checked: list[_CheckedClaim], conflicts: ConflictReport) -> FactCheckReport:
    """Combine grounding results and detected conflicts into claim statuses."""
    grounded = [c for c in checked if c.grounded]
    contested = {
        grounded[i].statement
        for conflict in conflicts.conflicts
        for i in conflict.claim_ids
        if 0 <= i < len(grounded)
    }

    def status(c: _CheckedClaim) -> ClaimStatus:
        if not c.grounded:
            return "unverified"
        return "contested" if c.statement in contested else "supported"

    claims = [
        VerifiedClaim(
            statement=c.statement,
            source_urls=c.source_urls,
            status=status(c),
            credibility=c.credibility,
        )
        for c in checked
    ]
    return FactCheckReport(claims=claims, conflicts=[c.explanation for c in conflicts.conflicts])


class FactChecker:
    """Marks each claim supported / contested / unverified."""

    def __init__(self, llm: LLMFactory) -> None:
        self.llm = llm

    def __call__(self, findings: list[Finding]) -> FactCheckReport:
        checked = ground_claims(findings)
        grounded = [c for c in checked if c.grounded]
        conflicts = ConflictReport()
        if len(grounded) >= 2:
            numbered = "\n".join(f"[{i}] {c.statement}" for i, c in enumerate(grounded))
            prompt = FACT_CHECK_PROMPT.format(claims=numbered)
            conflicts = self.llm.invoke_structured(
                ConflictReport, "reasoning", [HumanMessage(prompt)]
            )
        return build_report(checked, conflicts)
