"""Planner agent: research query -> ResearchPlan (notebook 02)."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from research_system.agents.base import today
from research_system.config.llm import LLMFactory
from research_system.prompts import PLANNER_HUMAN, PLANNER_SYSTEM
from research_system.schemas import ResearchPlan


class Planner:
    """Decomposes a query into 3-5 non-overlapping, searchable sub-questions."""

    def __init__(self, llm: LLMFactory) -> None:
        self.llm = llm

    def __call__(self, query: str) -> ResearchPlan:
        messages = [
            SystemMessage(PLANNER_SYSTEM.format(today=today())),
            HumanMessage(PLANNER_HUMAN.format(query=query)),
        ]
        return self.llm.invoke_structured(ResearchPlan, "reasoning", messages)
