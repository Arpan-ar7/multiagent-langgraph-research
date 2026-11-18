"""Writer agent (notebook 06): verified evidence -> Markdown draft with [n] citations.

The writer never sees or writes URLs; code numbers the sources and builds References.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from research_system.agents.base import today
from research_system.config.llm import LLMFactory
from research_system.prompts import WRITER_PROMPT
from research_system.schemas import Draft, FactCheckReport, ResearchPlan
from research_system.utils.citations import number_sources


def format_evidence(fact_check: FactCheckReport, numbers: dict[str, int]) -> str:
    """One line per usable claim: `- (status) statement [n][m]`."""
    lines = [
        f"- ({c.status}) {c.statement} " + "".join(f"[{numbers[u]}]" for u in c.source_urls)
        for c in fact_check.usable_claims()
    ]
    return "\n".join(lines) or "(no verified evidence)"


class Writer:
    """Synthesises a cited report following the planned outline."""

    def __init__(self, llm: LLMFactory, temperature: float = 0.3) -> None:
        self.llm = llm
        self.temperature = temperature

    def __call__(self, plan: ResearchPlan, fact_check: FactCheckReport) -> Draft:
        numbers = number_sources(fact_check)
        prompt = WRITER_PROMPT.format(
            today=today(),
            objective=plan.objective,
            outline=" | ".join(plan.report_outline),
            evidence=format_evidence(fact_check, numbers),
            conflicts="\n".join(f"- {c}" for c in fact_check.conflicts) or "None",
        )
        reply = self.llm.chat("worker", self.temperature).invoke([HumanMessage(prompt)])
        return Draft(markdown=str(reply.content), sources=numbers)
