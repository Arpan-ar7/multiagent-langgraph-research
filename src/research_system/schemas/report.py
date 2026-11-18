"""Writer output schema."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Draft(BaseModel):
    """Markdown draft with `[n]` markers and the URL -> number map the markers refer to."""

    markdown: str
    sources: dict[str, int] = Field(default_factory=dict)
