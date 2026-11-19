"""Streamlit front end for the research API.

    uv run research-api                          # terminal 1: the API on :8000
    uv run streamlit run ui/streamlit_app.py     # terminal 2: this UI

The UI only talks HTTP (via ResearchClient); it never imports the graph. Each rerun replays
the selected run's event log from the API, so the timeline survives page reloads and
reconnects, and runs keep going in the API if the browser tab is closed.
"""

from __future__ import annotations

import os
from typing import Any, Literal

import httpx
import streamlit as st

from research_system.api.client import ResearchClient
from research_system.ui.timeline import STAGES, Phase, StageState, Timeline
from research_system.utils.citations import linkify_citations

API_URL = os.getenv("RESEARCH_API_URL", "http://127.0.0.1:8000")
ICONS = {
    StageState.WAITING: "⚪",
    StageState.RUNNING: "🔵",
    StageState.DONE: "🟢",
    StageState.FAILED: "🔴",
}
BoxState = Literal["running", "complete", "error"]
BOX_STATES: dict[Phase, BoxState] = {Phase.ERROR: "error", Phase.REVIEW: "running"}
STATUS_BADGES = {
    "done": ":green-badge[done]",
    "awaiting_review": ":orange-badge[awaiting review]",
    "incomplete": ":red-badge[incomplete]",
    "new": ":gray-badge[new]",
}
EXAMPLES = [
    "Compare LangGraph and CrewAI for building multi-agent systems",
    "What are the main techniques for reducing LLM hallucinations?",
    "How has the adoption of heat pumps in Europe changed since 2020?",
]

st.set_page_config(page_title="Multi-Agent Research", page_icon="🔎", layout="wide")


@st.cache_resource
def get_client(url: str) -> ResearchClient:
    return ResearchClient(url)


api = get_client(API_URL)


def select_run(thread_id: str | None) -> None:
    st.session_state.thread_id = thread_id


# ---------------------------------------------------------------------- sidebar
def sidebar() -> dict[str, Any]:
    """Connection status, run settings and history; returns the chosen run options."""
    with st.sidebar:
        st.header("🔎 Research")
        try:
            health = api.health()
        except httpx.HTTPError:
            st.error(f"API not reachable at {API_URL}")
            st.code("uv run research-api", language="bash")
            st.stop()
        providers = " · ".join(
            f"{'✅' if ok else '➖'} {name}"  # noqa: RUF001
            for name, ok in health["providers"].items()
        )
        st.caption(f"API v{health['version']} · {providers}")

        st.button("➕ New research", on_click=select_run, args=(None,), width="stretch")  # noqa: RUF001

        defaults = health.get("defaults", {})
        with st.expander("Run settings", expanded=False):
            options = {
                "max_sub_questions": st.slider(
                    "Sub-questions",
                    1,
                    5,
                    defaults.get("max_sub_questions", 4),
                    help="How many parallel researchers the planner may start.",
                ),
                "max_tool_calls": st.slider(
                    "Searches per researcher", 1, 10, defaults.get("max_tool_calls", 4)
                ),
                "max_iterations": st.slider(
                    "Critic passes",
                    1,
                    4,
                    defaults.get("max_iterations", 2),
                    help="The critic can send researchers back to fill gaps this many times.",
                ),
                "approval_threshold": st.slider(
                    "Approval threshold",
                    1,
                    5,
                    defaults.get("approval_threshold", 4),
                    help="Minimum rubric score (1-5) the critic must give every criterion.",
                ),
                "human_review": st.toggle(
                    "Review the plan before research", defaults.get("human_review", False)
                ),
            }
            st.caption(
                "Each run costs roughly 8-15 LLM calls; "
                "fewer sub-questions and passes use less quota."
            )

        st.subheader("History")
        runs = api.list_runs(limit=15)
        if not runs:
            st.caption("No runs yet.")
        for run in runs:
            label = (run["query"] or run["thread_id"])[:48]
            icon = {"done": "📄", "awaiting_review": "⏸️", "incomplete": "⚠️"}.get(run["status"], "•")
            st.button(
                f"{icon} {label}",
                key=f"run-{run['thread_id']}",
                on_click=select_run,
                args=(run["thread_id"],),
                width="stretch",
                type="primary"
                if run["thread_id"] == st.session_state.get("thread_id")
                else "secondary",
            )
    return options


# ---------------------------------------------------------------------- new run
def new_run_form(options: dict[str, Any]) -> None:
    st.title("Multi-agent research")
    st.write(
        "A planner splits your question into sub-questions, parallel researchers search the "
        "web and academic sources, a fact-checker cross-checks the claims, a writer drafts a "
        "cited report and a critic sends it back for more research until it is good enough."
    )
    with st.form("new-run"):
        query = st.text_area(
            "Research question",
            key="query",
            height=100,
            placeholder="e.g. " + EXAMPLES[0],
        )
        submitted = st.form_submit_button("Start research", type="primary")
    with st.expander("Example questions"):
        for example in EXAMPLES:
            st.markdown(f"- {example}")
    if submitted:
        if len(query.strip()) < 5:
            st.warning("Please enter a question of at least 5 characters.")
            return
        try:
            select_run(api.start(query.strip(), **options))
        except httpx.HTTPStatusError as e:
            st.error(f"Could not start the run: {e.response.text}")
            return
        st.rerun()


# ---------------------------------------------------------------------- timeline
def render_timeline(timeline: Timeline) -> None:
    columns = st.columns(len(STAGES))
    for column, (stage, label) in zip(columns, STAGES.items(), strict=True):
        extra = (
            f" ×{timeline.critic_passes}"  # noqa: RUF001
            if stage == "critic" and timeline.critic_passes > 1
            else ""
        )
        column.markdown(f"{ICONS[timeline.stages[stage]]} **{label}**{extra}")
    for number, researchers in enumerate(timeline.rounds, start=1):
        title = "Researchers" if number == 1 else f"Follow-up round {number - 1}"
        st.caption(title)
        for question, state in researchers.items():
            st.markdown(f"{ICONS[state]} {question}")
    if timeline.log:
        with st.expander("Activity log", expanded=False):
            st.text("\n".join(timeline.log))


def follow(thread_id: str, active: bool) -> Timeline:
    """Replay the run's events and keep rendering while it executes."""
    timeline = Timeline()
    label = "Agents working…" if active else "Run timeline"
    with st.status(label, expanded=active) as box:
        area = st.empty()
        try:
            for event in api.events(thread_id, after=0):
                timeline.apply(event)
                with area.container():
                    render_timeline(timeline)
        except httpx.HTTPError as e:
            st.warning(f"Lost the live connection ({type(e).__name__}); reload to reconnect.")
        if not timeline.log:
            area.caption("No live events for this run (it ran before the API last restarted).")
        state: BoxState = BOX_STATES.get(timeline.phase, "complete")
        box.update(
            label=_timeline_label(timeline), state=state, expanded=timeline.phase is Phase.ERROR
        )
    return timeline


def _timeline_label(timeline: Timeline) -> str:
    match timeline.phase:
        case Phase.DONE:
            return "Run complete"
        case Phase.REVIEW:
            return "Waiting for plan approval"
        case Phase.ERROR:
            return "Run stopped"
    return "Run timeline"


# ---------------------------------------------------------------------- run states
def plan_review(thread_id: str, run: dict[str, Any]) -> None:
    plan = run["plan"]
    st.subheader("Review the research plan")
    st.write(f"**Objective:** {plan['objective']}")
    st.caption("Untick sub-questions you don't need. Fewer sub-questions also use less quota.")
    with st.form("review"):
        keep = [
            q["question"]
            for i, q in enumerate(plan["sub_questions"])
            if st.checkbox(
                f"{q['question']}  \n:gray[{q['search_strategy']} · {q['rationale']}]",
                value=True,
                key=f"sq-{thread_id}-{i}",
            )
        ]
        approved = st.form_submit_button("Approve and research", type="primary")
    if approved:
        if not keep:
            st.warning("Keep at least one sub-question.")
            return
        everything = len(keep) == len(plan["sub_questions"])
        api.review(thread_id, None if everything else keep)
        st.rerun()


def incomplete(thread_id: str, run: dict[str, Any], timeline: Timeline) -> None:
    st.error(timeline.error or "This run stopped before finishing.")
    st.write(
        "Finished steps are checkpointed, so resuming continues from the step that failed "
        "(for example after the free-tier daily quota resets)."
    )
    if st.button("▶ Resume run", type="primary"):
        api.resume(thread_id)
        st.rerun()


def results(run: dict[str, Any]) -> None:
    report: str = run["report"]
    numbers = {s["url"]: s["n"] for s in run["sources"]}
    tab_report, tab_sources, tab_plan, tab_stats = st.tabs(
        ["📄 Report", f"🔗 Sources ({len(numbers)})", "🧭 Plan & critique", "⏱ Run stats"]
    )
    with tab_report:
        st.download_button(
            "Download Markdown", report, file_name=f"{run['thread_id']}.md", mime="text/markdown"
        )
        body, _, _ = report.partition("\n## References")
        st.markdown(linkify_citations(body, numbers))
        _, _, rest = report.partition("\n## References")
        if rest:
            st.markdown("## References" + rest)

    with tab_sources:
        if run["sources"]:
            st.dataframe(
                run["sources"],
                hide_index=True,
                width="stretch",
                column_order=["n", "domain", "credibility", "claims", "contested", "url"],
                column_config={
                    "n": st.column_config.NumberColumn("#", width="small"),
                    "credibility": st.column_config.ProgressColumn(
                        "Credibility",
                        min_value=0.0,
                        max_value=1.0,
                        format="%.1f",
                        help="Rule-based: academic/.gov/.edu 0.9, reference sites 0.7, other 0.5",
                    ),
                    "claims": st.column_config.NumberColumn("Claims supported"),
                    "contested": st.column_config.NumberColumn("Contested"),
                    "url": st.column_config.LinkColumn("URL"),
                },
            )
        else:
            st.caption("No sources were cited.")

    with tab_plan:
        plan = run.get("plan")
        if plan:
            st.write(f"**Objective:** {plan['objective']}  \n**Type:** {plan['research_type']}")
            for q in plan["sub_questions"]:
                st.markdown(f"- {q['question']} :gray[({q['search_strategy']})]")
        critique = run.get("critique")
        if critique:
            st.subheader("Critic's last review")
            a, b, c = st.columns(3)
            a.metric("Coverage", f"{critique['coverage']}/5")
            b.metric("Evidence use", f"{critique['evidence_use']}/5")
            c.metric("Coherence", f"{critique['coherence']}/5")
            st.write(critique["justification"])
            if critique["gaps"]:
                st.markdown("**Remaining gaps**\n" + "\n".join(f"- {g}" for g in critique["gaps"]))

    with tab_stats:
        timings = run["timings"]
        total = sum(t["seconds"] for t in timings)
        a, b, c = st.columns(3)
        a.metric(
            "Agent time",
            f"{total:.0f} s",
            help="Sum of step durations; researchers run in parallel, so wall time is lower.",
        )
        b.metric("Sources cited", len(numbers))
        c.metric(
            "Researcher calls", next((t["count"] for t in timings if t["node"] == "researcher"), 0)
        )
        if timings:
            st.bar_chart(
                {t["node"]: t["seconds"] for t in timings},
                horizontal=True,
                y_label="",
                x_label="seconds",
            )
        for message in run["warnings"] + [f"Could not research: {f}" for f in run["failures"]]:
            st.warning(message)


def show_run(thread_id: str) -> None:
    try:
        run = api.get(thread_id)
    except httpx.HTTPStatusError:
        st.error("Run not found.")
        select_run(None)
        return
    st.title(run["query"] or "Research run")
    st.caption(f"{STATUS_BADGES.get(run['status'], run['status'])} · thread `{thread_id}`")

    timeline = follow(thread_id, run["active"])
    run = api.get(thread_id)  # state after the live stream ended

    if run["active"]:
        st.info("Still running; reconnecting…")
        st.rerun()
    elif run["status"] == "awaiting_review":
        plan_review(thread_id, run)
    elif run["status"] == "incomplete":
        incomplete(thread_id, run, timeline)
    elif run["status"] == "done":
        results(run)


options = sidebar()
if st.session_state.get("thread_id"):
    show_run(st.session_state.thread_id)
else:
    new_run_form(options)
