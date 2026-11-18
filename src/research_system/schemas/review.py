"""Fact-checker and critic schemas (notebook 06)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ClaimStatus = Literal["supported", "contested", "unverified"]


class Conflict(BaseModel):
    """Two claims that cannot both be true as stated."""

    claim_ids: list[int] = Field(
        min_length=2, max_length=2, description="Ids of the two conflicting claims"
    )
    explanation: str = Field(description="Why they conflict and what could explain the difference")


class ConflictReport(BaseModel):
    """LLM output of the fact-checker's contradiction check."""

    conflicts: list[Conflict] = Field(default_factory=list, description="Empty if no conflicts")


class VerifiedClaim(BaseModel):
    """A claim after fact-checking."""

    statement: str
    source_urls: list[str]
    status: ClaimStatus
    credibility: float = Field(ge=0.0, le=1.0)


class FactCheckReport(BaseModel):
    """Fact-checker output passed to the writer."""

    claims: list[VerifiedClaim]
    conflicts: list[str] = Field(default_factory=list)

    def usable_claims(self) -> list[VerifiedClaim]:
        """Claims the writer may use (unverified ones are excluded)."""
        return [c for c in self.claims if c.status != "unverified"]


class Critique(BaseModel):
    """Rubric-based evaluation of a research report."""

    coverage: int = Field(
        ge=1, le=5, description="Does the report answer every part of the objective?"
    )
    evidence_use: int = Field(
        ge=1, le=5, description="Are claims supported by citations; contested points flagged?"
    )
    coherence: int = Field(
        ge=1, le=5, description="Is it well structured, clear and non-repetitive?"
    )
    justification: str = Field(description="2-3 sentences explaining the scores")
    gaps: list[str] = Field(default_factory=list, description="Specific missing information")
    follow_up_questions: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Up to 3 searchable questions that would fill the gaps",
    )

    def approved(self, threshold: int) -> bool:
        """Approval is decided by code from the scores, not by the model."""
        return min(self.coverage, self.evidence_use, self.coherence) >= threshold
