"""Pydantic data contracts exchanged between agents."""

from research_system.schemas.findings import Claim, Finding
from research_system.schemas.plan import ResearchPlan, SubQuestion
from research_system.schemas.report import Draft
from research_system.schemas.review import (
    Conflict,
    ConflictReport,
    Critique,
    FactCheckReport,
    VerifiedClaim,
)
from research_system.schemas.search import SearchResult

ALL_SCHEMAS: tuple[type, ...] = (
    Claim,
    Conflict,
    ConflictReport,
    Critique,
    Draft,
    FactCheckReport,
    Finding,
    ResearchPlan,
    SearchResult,
    SubQuestion,
    VerifiedClaim,
)
"""Types allowed to be deserialised from checkpoints (see graph/checkpointing.py)."""

__all__ = [
    "ALL_SCHEMAS",
    "Claim",
    "Conflict",
    "ConflictReport",
    "Critique",
    "Draft",
    "FactCheckReport",
    "Finding",
    "ResearchPlan",
    "SearchResult",
    "SubQuestion",
    "VerifiedClaim",
]
