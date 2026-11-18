"""Agents finalised in notebooks 02, 04 and 06, shared by notebooks 07-08.

Staging area for src/research_system/agents/ and prompts/ (Phase 2). Each agent is a
plain function with typed inputs/outputs, so the graph can receive them as a dependency
(and tests can swap in stubs).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal
from urllib.parse import urlparse

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from nb_components import RESEARCH_TOOLS, ResearchPlan, llm_for, role_models, structured
from pydantic import BaseModel, Field

URL_RE = re.compile(r"URL: (\S+)")

# =========================================================================== schemas


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
    confidence: Literal["high", "medium", "low"] = Field(
        description="high = multiple agreeing sources"
    )
    gaps: list[str] = Field(default_factory=list, description="What could not be found or verified")
    retrieved_urls: list[str] = Field(
        default_factory=list, description="Filled by code, not the model"
    )


class VerifiedClaim(BaseModel):
    statement: str
    source_urls: list[str]
    status: Literal["supported", "contested", "unverified"]
    credibility: float


class FactCheckReport(BaseModel):
    claims: list[VerifiedClaim]
    conflicts: list[str]


class Conflict(BaseModel):
    """Two claims that cannot both be true as stated."""

    claim_ids: list[int] = Field(
        min_length=2, max_length=2, description="Ids of the two conflicting claims"
    )
    explanation: str = Field(description="Why they conflict and what could explain the difference")


class ConflictReport(BaseModel):
    conflicts: list[Conflict] = Field(default_factory=list, description="Empty if no conflicts")


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

    def approved(self, threshold: int = 4) -> bool:
        return min(self.coverage, self.evidence_use, self.coherence) >= threshold


# =========================================================================== prompts

PLANNER_SYSTEM = """You are a senior research strategist. Today's date is {today}.

Your task: turn the user's research query into an actionable research plan.

Steps:
1. Restate the objective precisely and classify the research type.
2. Decompose it into 3-5 sub-questions that together fully answer the objective.
3. For each, choose the best source type (web, academic, encyclopedic).
4. Propose a logical outline for the final report.

Constraints:
- Sub-questions must NOT overlap; each must be answerable independently by a separate researcher.
- Prefer concrete, searchable phrasing over vague themes.
- For anything time-sensitive, mention the timeframe explicitly (relative to today's date)."""

RESEARCHER_SYSTEM = """You are a meticulous research analyst. Today's date is {today}.

Your job: answer ONE research sub-question with evidence. Preferred source type: {strategy}.

Process:
1. Search with specific queries (entities, years). Prefer primary/authoritative sources.
2. Use search_papers for scientific questions, search_wikipedia only for background definitions.
3. Use fetch_page only if a snippet is promising but too short.
4. Stop when you have 2-4 good sources, then respond with your Finding.

Rules:
- Every claim must cite URL(s) that appeared in your tool results. Never invent URLs.
- If a tool returns an ERROR, switch to another tool.
- Record anything you could not verify under gaps."""

FACT_CHECK_PROMPT = """You are a rigorous fact-checker. Below are numbered claims gathered by different researchers.
Identify pairs of claims that CONTRADICT each other (they cannot both be true as stated).
Differences in scope or wording that can both be true are NOT conflicts.
Return an empty list if there are no real contradictions.

Claims:
{claims}"""

WRITER_PROMPT = """You are an expert research writer. Today's date is {today}.
Write a well-structured Markdown research report.

Objective: {objective}
Use these section headings, in order: {outline}

Evidence (each line ends with its citation markers):
{evidence}

Known conflicts between sources:
{conflicts}

Rules:
- Use ONLY the evidence above. Do not add facts from memory.
- Cite with the given markers like [1] or [2][3] right after the sentence they support. Never write URLs.
- Claims marked (contested) must be presented as disputed, mentioning the disagreement.
- Start with a '# ' title. Be concise: about 400-600 words. Do NOT write a references section."""

CRITIC_PROMPT = """You are a demanding research editor. Evaluate the report against the objective.
Score strictly: 5 = excellent, 3 = acceptable with clear weaknesses, 1 = poor.
Only propose follow-up questions for gaps that new web/academic research could realistically fill.

Objective: {objective}
Planned sub-questions:
{sub_questions}

Report:
{report}"""


def today() -> str:
    return date.today().isoformat()


# =========================================================================== agents


def plan(query: str) -> ResearchPlan:
    """Planner agent (nb 02): query -> ResearchPlan."""
    prompt = ChatPromptTemplate.from_messages(
        [("system", PLANNER_SYSTEM), ("human", "Research query: {query}")]
    )
    return (prompt | structured(ResearchPlan, "reasoning")).invoke(
        {"today": today(), "query": query}
    )


def research(
    sub_question: str, strategy: str = "web", max_tool_calls: int = 4, max_model_calls: int = 7
) -> Finding:
    """Researcher agent (nb 04): one sub-question -> Finding with code-filled retrieved_urls."""
    worker, *backups = role_models("worker")
    agent = create_agent(
        model=worker,
        tools=RESEARCH_TOOLS,
        system_prompt=RESEARCHER_SYSTEM.format(today=today(), strategy=strategy),
        response_format=ToolStrategy(Finding),
        middleware=[
            ModelFallbackMiddleware(*backups),
            ToolCallLimitMiddleware(run_limit=max_tool_calls),
            ModelCallLimitMiddleware(run_limit=max_model_calls),
        ],
    )
    result = agent.invoke({"messages": [HumanMessage(sub_question)]})
    finding: Finding | None = result.get("structured_response")
    if finding is None:
        raise RuntimeError("researcher ended without a structured Finding (call limit reached?)")
    seen = {
        u
        for m in result["messages"]
        if isinstance(m, ToolMessage)
        for u in URL_RE.findall(str(m.content))
    }
    return finding.model_copy(update={"sub_question": sub_question, "retrieved_urls": sorted(seen)})


HIGH = ("arxiv.org", ".gov", ".edu", "nature.com", "acm.org", "ieee.org")
MEDIUM = ("wikipedia.org", "github.com", "reuters.com", "apnews.com")


def credibility(url: str) -> float:
    host = urlparse(url).netloc.lower()
    return 0.9 if any(h in host for h in HIGH) else 0.7 if any(m in host for m in MEDIUM) else 0.5


def fact_check(findings: list[Finding]) -> FactCheckReport:
    """Fact-checker (nb 06): deterministic grounding + one LLM call for contradictions."""
    rows = [
        {
            "statement": c.statement,
            "source_urls": c.source_urls,
            "grounded": all(u in f.retrieved_urls for u in c.source_urls),
            "credibility": max(credibility(u) for u in c.source_urls),
        }
        for f in findings
        for c in f.claims
    ]
    grounded = [r for r in rows if r["grounded"]]
    conflicts = ConflictReport()
    if len(grounded) >= 2:
        numbered = "\n".join(f"[{i}] {r['statement']}" for i, r in enumerate(grounded))
        conflicts = structured(ConflictReport, "reasoning").invoke(
            FACT_CHECK_PROMPT.format(claims=numbered)
        )
    contested = {
        grounded[i]["statement"]
        for c in conflicts.conflicts
        for i in c.claim_ids
        if i < len(grounded)
    }
    claims = [
        VerifiedClaim(
            statement=r["statement"],
            source_urls=r["source_urls"],
            credibility=r["credibility"],
            status="unverified"
            if not r["grounded"]
            else "contested"
            if r["statement"] in contested
            else "supported",
        )
        for r in rows
    ]
    return FactCheckReport(claims=claims, conflicts=[c.explanation for c in conflicts.conflicts])


def number_sources(fc: FactCheckReport) -> dict[str, int]:
    numbers: dict[str, int] = {}
    for c in fc.claims:
        if c.status != "unverified":
            for u in c.source_urls:
                numbers.setdefault(u, len(numbers) + 1)
    return numbers


def write(research_plan: ResearchPlan, fc: FactCheckReport) -> tuple[str, dict[str, int]]:
    """Writer (nb 06): returns (markdown draft with [n] markers, source->number map)."""
    numbers = number_sources(fc)
    evidence = "\n".join(
        f"- ({c.status}) {c.statement} " + " ".join(f"[{numbers[u]}]" for u in c.source_urls)
        for c in fc.claims
        if c.status != "unverified"
    )
    draft = (
        llm_for("worker", temperature=0.3)
        .invoke(
            WRITER_PROMPT.format(
                today=today(),
                objective=research_plan.objective,
                outline=" | ".join(research_plan.report_outline),
                evidence=evidence or "(no verified evidence)",
                conflicts="\n".join(f"- {c}" for c in fc.conflicts) or "None",
            )
        )
        .content
    )
    return draft, numbers


def critique(research_plan: ResearchPlan, report: str) -> Critique:
    """Critic (nb 06): rubric scores + follow-up questions."""
    return structured(Critique, "reasoning").invoke(
        CRITIC_PROMPT.format(
            objective=research_plan.objective,
            report=report,
            sub_questions="\n".join(f"- {s.question}" for s in research_plan.sub_questions),
        )
    )


def finalize(markdown: str, numbers: dict[str, int]) -> tuple[str, list[str]]:
    """Validate [n] markers and append a References section built by code."""
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", markdown)}
    valid = set(numbers.values())
    problems = [f"invalid citation [{n}]" for n in sorted(cited - valid)]
    problems += [f"source [{n}] never cited" for n in sorted(valid - cited)]
    refs = "\n".join(f"{n}. {url}" for url, n in sorted(numbers.items(), key=lambda kv: kv[1]))
    return f"{markdown.rstrip()}\n\n## References\n{refs}\n", problems


# =========================================================================== dependency container


@dataclass
class Agents:
    """All agent callables the graph needs. Swap any of them for a stub in tests."""

    plan: Callable[[str], ResearchPlan] = plan
    research: Callable[..., Finding] = research
    fact_check: Callable[[list[Finding]], FactCheckReport] = fact_check
    write: Callable[[ResearchPlan, FactCheckReport], tuple[str, dict[str, int]]] = write
    critique: Callable[[ResearchPlan, str], Critique] = critique
