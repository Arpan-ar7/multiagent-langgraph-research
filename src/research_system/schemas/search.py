"""Provider-independent search result (notebook 03)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SourceProvider = Literal["tavily", "duckduckgo", "arxiv", "wikipedia"]


class SearchResult(BaseModel):
    """One search hit; the unit of evidence that flows through the system."""

    title: str
    url: str
    content: str = Field(description="Snippet or extracted text")
    source: SourceProvider
    score: float | None = None
    published: str | None = None
