"""Evaluation metrics: deterministic report metrics, usage counting and the LLM judge."""

from __future__ import annotations

import re
import threading
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from research_system.config.llm import LLMFactory
from research_system.utils.citations import validate_citations
from research_system.utils.sources import domain

# ---------------------------------------------------------------- deterministic (free, objective)


def report_metrics(values: dict[str, Any]) -> dict[str, Any]:
    """Objective metrics computed from a finished run's state."""
    fact_check = values["fact_check"]
    draft = values["draft"]
    critique = values["critique"]
    statuses = [c.status for c in fact_check.claims]
    sources = list(draft.sources)
    return {
        "claims": len(statuses),
        "grounding_rate": round(
            sum(s != "unverified" for s in statuses) / max(len(statuses), 1), 3
        ),
        "contested_claims": statuses.count("contested"),
        "sources_cited": len(sources),
        "distinct_domains": len({domain(u) for u in sources}),
        "mean_credibility": round(
            sum(c.credibility for c in fact_check.claims) / max(len(fact_check.claims), 1), 3
        ),
        "citation_problems": len(validate_citations(draft.markdown, draft.sources)),
        "failed_researchers": len(values.get("failures", [])),
        "warnings": len(values.get("warnings", [])),
        "critic_iterations": values.get("iteration", 0),
        "critic_min_score": min(critique.coverage, critique.evidence_use, critique.coherence),
        "words": len(re.findall(r"\w+", draft.markdown)),
    }


class UsageCounter(BaseCallbackHandler):
    """Counts chat-model calls and tokens across a graph run, including parallel threads."""

    def __init__(self) -> None:
        self.calls = 0
        self.tokens = 0
        self._lock = threading.Lock()

    def on_chat_model_start(self, serialized: Any, messages: Any, **kwargs: Any) -> None:
        with self._lock:
            self.calls += 1

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        total = 0
        for generations in response.generations:
            for gen in generations:
                usage = getattr(getattr(gen, "message", None), "usage_metadata", None) or {}
                total += usage.get("total_tokens", 0)
        with self._lock:
            self.tokens += total


# ---------------------------------------------------------------- LLM-as-judge (subjective)


class JudgeScore(BaseModel):
    """Evaluation of a research report by an independent reviewer."""

    relevance: int = Field(
        ge=1, le=5, description="1 = off-topic, 3 = partly answers, 5 = directly answers"
    )
    completeness: int = Field(
        ge=1, le=5, description="1 = major aspects missing, 3 = main points only, 5 = thorough"
    )
    specificity: int = Field(
        ge=1,
        le=5,
        description="1 = vague generalities, 3 = some specifics, 5 = concrete facts and numbers",
    )
    rationale: str = Field(description="One or two sentences justifying the scores")


JUDGE_PROMPT = """\
You are an impartial expert reviewer. Score the research report below as an answer to the question.
Judge only what is written. Ignore formatting. Be strict and use the full 1-5 range.

Question: {question}

Report:
{report}"""


class Judge:
    """LLM-as-judge on the dedicated `judge` model chain (independent of writer/critic)."""

    def __init__(self, llm: LLMFactory, max_report_chars: int = 12_000) -> None:
        self.llm = llm
        self.max_report_chars = max_report_chars

    def __call__(self, question: str, report: str) -> JudgeScore:
        prompt = JUDGE_PROMPT.format(question=question, report=report[: self.max_report_chars])
        return self.llm.invoke_structured(JudgeScore, "judge", [HumanMessage(prompt)])
