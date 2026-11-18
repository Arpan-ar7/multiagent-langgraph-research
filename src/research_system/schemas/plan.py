"""Planner output schema (designed in notebook 02).

Field descriptions are sent to the LLM as part of the structured-output schema,
so they are written as instructions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SearchStrategy = Literal["web", "academic", "encyclopedic"]
ResearchType = Literal["factual", "comparative", "technical", "trend_analysis", "exploratory"]


class SubQuestion(BaseModel):
    """One focused, independently searchable research question."""

    question: str = Field(
        description="A specific, search-friendly question answerable via web or paper search"
    )
    rationale: str = Field(
        description="Why this question is needed to answer the main objective (one sentence)"
    )
    search_strategy: SearchStrategy = Field(
        description=(
            "web = news/blogs/docs, academic = research papers, "
            "encyclopedic = definitions/background"
        )
    )


class ResearchPlan(BaseModel):
    """A plan that decomposes a research query into focused sub-questions and a report outline."""

    objective: str = Field(description="The research objective restated in one precise sentence")
    research_type: ResearchType
    # The LLM is asked for 3-5 (description); the invariant is 1-5 because users and run
    # options may legitimately narrow a plan down (e.g. --sub-questions 2, plan review).
    sub_questions: list[SubQuestion] = Field(
        min_length=1,
        max_length=5,
        description="3-5 non-overlapping sub-questions covering the objective",
    )
    report_outline: list[str] = Field(
        min_length=3, max_length=7, description="Section headings for the final report"
    )

    @field_validator("sub_questions")
    @classmethod
    def _unique_questions(cls, value: list[SubQuestion]) -> list[SubQuestion]:
        texts = [s.question.strip().lower() for s in value]
        if len(set(texts)) != len(texts):
            raise ValueError("sub_questions must be unique")
        return value

    def with_sub_questions(self, sub_questions: list[SubQuestion]) -> ResearchPlan:
        """Copy with different sub-questions, *validated*.

        Never use `model_copy(update=...)` for this: it skips validation, and an invalid model
        is later restored from checkpoints via `model_construct`, leaving nested dicts.
        """
        return ResearchPlan.model_validate({**self.model_dump(), "sub_questions": sub_questions})
