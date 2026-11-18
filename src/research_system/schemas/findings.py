"""Researcher output schemas (notebooks 04 and 06)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]


class Claim(BaseModel):
    """A single factual statement and the sources that support it."""

    statement: str = Field(description="One specific, verifiable factual statement")
    source_urls: list[str] = Field(
        min_length=1, description="URL(s) from the tool results that support the statement"
    )


class Finding(BaseModel):
    """The researcher's evidence-backed answer to one sub-question."""

    sub_question: str
    summary: str = Field(description="2-4 sentence answer to the sub-question")
    claims: list[Claim] = Field(min_length=1, max_length=6)
    confidence: Confidence = Field(description="high = multiple agreeing sources")
    gaps: list[str] = Field(default_factory=list, description="What could not be found or verified")
    retrieved_urls: list[str] = Field(
        default_factory=list,
        description="Filled by code from the tool outputs, never by the model",
    )
