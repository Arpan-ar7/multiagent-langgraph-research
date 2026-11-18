"""The multi-agent research graph (notebook 07).

    planner -> human_review -(Send xN)-> researcher -> fact_checker -> writer -> critic
                                             ^                                    |
                                             +--- follow-up questions (Send) -----+
                                                                 approved/limit -> finalize

Nodes are thin wrappers: read state -> call an injected agent -> return a partial update,
plus progress events (custom stream) and timing metrics.
"""

from __future__ import annotations

import time
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.errors import NodeError
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, RetryPolicy, Send, interrupt

from research_system.agents.base import Agents
from research_system.graph.options import RunOptions
from research_system.graph.state import ResearcherTask, ResearchState
from research_system.schemas import FactCheckReport, VerifiedClaim
from research_system.utils.citations import assemble_report
from research_system.utils.errors import describe, is_retryable
from research_system.utils.logging import get_logger
from research_system.utils.sources import credibility

log = get_logger(__name__)

LLM_RETRY = RetryPolicy(
    max_attempts=3, initial_interval=2.0, backoff_factor=2.0, retry_on=is_retryable
)


def _emit(agent: str, status: str, **data: Any) -> None:
    """Progress event for `stream_mode="custom"` consumers (CLI, API, UI)."""
    get_stream_writer()({"agent": agent, "status": status, **data})


def _metric(node: str, start: float, **extra: Any) -> dict[str, Any]:
    end = time.perf_counter()
    return {"node": node, "start": start, "end": end, "seconds": round(end - start, 2), **extra}


def build_research_graph(
    agents: Agents,
    defaults: RunOptions | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Compile the research graph with injected agents and default run options."""
    defaults = defaults or RunOptions()

    def opts(state: ResearchState) -> RunOptions:
        return RunOptions.from_state(state, defaults)

    # ------------------------------------------------------------------ nodes
    def planner(state: ResearchState) -> dict[str, Any]:
        _emit("planner", "planning")
        t0 = time.perf_counter()
        options = opts(state)
        plan = agents.plan(state["query"])
        plan = plan.with_sub_questions(plan.sub_questions[: options.max_sub_questions])
        log.info("plan_ready", sub_questions=len(plan.sub_questions))
        return {
            "plan": plan,
            "options": options.model_dump(),
            "iteration": 0,
            "metrics": [_metric("planner", t0)],
        }

    def human_review(state: ResearchState) -> dict[str, Any]:
        if not opts(state).human_review:
            return {}
        plan = state["plan"]
        decision = interrupt(
            {"objective": plan.objective, "sub_questions": [q.question for q in plan.sub_questions]}
        )
        selected = (decision or {}).get("sub_questions")
        if selected:
            kept = [q for q in plan.sub_questions if q.question in selected]
            if kept:
                return {"plan": plan.with_sub_questions(kept)}
        return {}

    def researcher(task: ResearcherTask) -> dict[str, Any]:
        # Send tasks bypass node error handlers (notebook 05 §9c), so failures are caught here.
        question = task["sub_question"]
        _emit("researcher", "started", sub_question=question)
        t0 = time.perf_counter()
        try:
            finding = agents.research(
                question, task["strategy"], max_tool_calls=task["max_tool_calls"]
            )
        except Exception as e:
            log.warning("researcher_failed", sub_question=question, error=describe(e))
            _emit("researcher", "failed", sub_question=question)
            return {
                "failures": [f"{question} ({describe(e, 120)})"],
                "metrics": [_metric("researcher", t0, ok=False)],
            }
        _emit("researcher", "done", sub_question=question, claims=len(finding.claims))
        return {"findings": [finding], "metrics": [_metric("researcher", t0, ok=True)]}

    def fact_checker(state: ResearchState) -> dict[str, Any]:
        findings = state.get("findings", [])
        _emit("fact_checker", "checking", findings=len(findings))
        t0 = time.perf_counter()
        return {"fact_check": agents.fact_check(findings), "metrics": [_metric("fact_checker", t0)]}

    def writer(state: ResearchState) -> dict[str, Any]:
        _emit("writer", "writing")
        t0 = time.perf_counter()
        draft = agents.write(state["plan"], state["fact_check"])
        return {"draft": draft, "metrics": [_metric("writer", t0)]}

    def critic(state: ResearchState) -> dict[str, Any]:
        _emit("critic", "reviewing")
        t0 = time.perf_counter()
        critique = agents.critique(state["plan"], state["draft"].markdown)
        return {
            "critique": critique,
            "iteration": state.get("iteration", 0) + 1,
            "metrics": [_metric("critic", t0)],
        }

    def finalize(state: ResearchState) -> dict[str, Any]:
        limitations = [f"Could not research: {f}" for f in state.get("failures", [])]
        limitations += state.get("warnings", [])
        draft = state["draft"]
        report, problems = assemble_report(draft.markdown, draft.sources, limitations)
        _emit("finalize", "done", citation_problems=len(problems))
        return {"report": report}

    # ------------------------------------------------------------------ graceful degradation
    def fact_check_failed(state: ResearchState, error: NodeError) -> Command[Any]:
        claims = [
            VerifiedClaim(
                statement=c.statement,
                source_urls=c.source_urls,
                status="supported",
                credibility=max(credibility(u) for u in c.source_urls),
            )
            for f in state.get("findings", [])
            for c in f.claims
        ]
        warning = (
            f"Fact-checking skipped ({type(error.error).__name__}); claims were not cross-verified."
        )
        return Command(
            update={"fact_check": FactCheckReport(claims=claims), "warnings": [warning]},
            goto="writer",
        )

    def critic_failed(state: ResearchState, error: NodeError) -> Command[Any]:
        warning = f"Quality review skipped ({type(error.error).__name__})."
        return Command(update={"warnings": [warning]}, goto="finalize")

    # ------------------------------------------------------------------ routing
    def task(state: ResearchState, question: str, strategy: str) -> Send:
        limit = opts(state).max_tool_calls
        return Send(
            "researcher",
            ResearcherTask(sub_question=question, strategy=strategy, max_tool_calls=limit),
        )

    def dispatch_researchers(state: ResearchState) -> list[Send]:
        return [task(state, q.question, q.search_strategy) for q in state["plan"].sub_questions]

    def after_critic(state: ResearchState) -> str | list[Send]:
        o = opts(state)
        critique = state["critique"]
        if (
            critique.approved(o.approval_threshold)
            or state["iteration"] >= o.max_iterations
            or not critique.follow_up_questions
        ):
            return "finalize"
        return [task(state, q, "web") for q in critique.follow_up_questions]

    # ------------------------------------------------------------------ wiring
    g = StateGraph(ResearchState)
    g.add_node("planner", planner, retry_policy=LLM_RETRY)
    g.add_node("human_review", human_review)
    # Send targets receive a private payload (ResearcherTask), not the shared state.
    g.add_node("researcher", researcher, input_schema=ResearcherTask)  # type: ignore[arg-type]
    g.add_node(
        "fact_checker", fact_checker, retry_policy=LLM_RETRY, error_handler=fact_check_failed
    )
    g.add_node("writer", writer, retry_policy=LLM_RETRY)
    g.add_node("critic", critic, retry_policy=LLM_RETRY, error_handler=critic_failed)
    g.add_node("finalize", finalize)

    g.add_edge(START, "planner")
    g.add_edge("planner", "human_review")
    g.add_conditional_edges("human_review", dispatch_researchers, ["researcher"])
    g.add_edge("researcher", "fact_checker")
    g.add_edge("fact_checker", "writer")
    g.add_edge("writer", "critic")
    g.add_conditional_edges("critic", after_critic, ["researcher", "finalize"])
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
