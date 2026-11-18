"""Critic agent (notebook 06): rubric scores + follow-up questions.

The model only scores; approval is decided by code (`Critique.approved(threshold)`).
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from research_system.config.llm import LLMFactory
from research_system.prompts import CRITIC_PROMPT
from research_system.schemas import Critique, ResearchPlan


class Critic:
    """Grades a report against the plan and proposes follow-up research."""

    def __init__(self, llm: LLMFactory) -> None:
        self.llm = llm

    def __call__(self, plan: ResearchPlan, report: str) -> Critique:
        prompt = CRITIC_PROMPT.format(
            objective=plan.objective,
            sub_questions="\n".join(f"- {s.question}" for s in plan.sub_questions),
            report=report,
        )
        return self.llm.invoke_structured(Critique, "reasoning", [HumanMessage(prompt)])
