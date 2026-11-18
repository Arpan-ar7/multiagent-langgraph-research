"""The real compiled graph, driven by stub agents: orchestration, failures, loops, resume."""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from research_system.config.settings import Settings
from research_system.graph import (
    RunOptions,
    build_research_graph,
    sqlite_checkpointer,
    thread_config,
)
from research_system.schemas import SubQuestion
from research_system.service import ResearchService, RunStatus
from tests.conftest import GOOD, WEAK, StubAgents

pytestmark = pytest.mark.integration


def run(stubs: StubAgents, **options: object) -> dict:
    graph = build_research_graph(stubs.agents(), RunOptions(), InMemorySaver())
    opts = RunOptions(**options).model_dump()  # type: ignore[arg-type]
    return graph.invoke({"query": "widgets", "options": opts}, thread_config("t"))


class TestHappyPath:
    def test_full_run_produces_cited_report(self, stubs: StubAgents) -> None:
        out = run(stubs)
        assert stubs.calls == {"plan": 1, "research": 3, "fact_check": 1, "write": 1, "critique": 1}
        assert out["iteration"] == 1
        assert "## References" in out["report"]
        assert "https://example.org/costs" in out["report"]
        assert "Limitations" not in out["report"]

    def test_sub_question_limit_caps_parallel_researchers(self, stubs: StubAgents) -> None:
        run(stubs, max_sub_questions=2)
        # Researchers run in parallel, so completion order is not deterministic.
        assert sorted(stubs.researched) == ["adoption", "costs"]

    def test_tool_call_limit_reaches_each_researcher(self, stubs: StubAgents) -> None:
        run(stubs, max_tool_calls=2)
        assert stubs.tool_limits == [2, 2, 2]


class TestFailures:
    def test_failed_researcher_is_reported_not_fatal(self, stubs: StubAgents) -> None:
        stubs.failing_questions = {"adoption"}
        out = run(stubs)
        assert len(out["findings"]) == 2
        assert "Could not research: adoption (ConnectionError" in out["report"]

    def test_fact_check_failure_degrades_to_writer(self, stubs: StubAgents) -> None:
        stubs.fact_check_error = ValueError("model returned garbage")  # not retryable
        out = run(stubs)
        assert stubs.calls["fact_check"] == 1
        assert "Fact-checking skipped (ValueError)" in out["report"]
        assert "## References" in out["report"]

    def test_transient_fact_check_error_is_retried(self, stubs: StubAgents) -> None:
        stubs.fact_check_error = ConnectionError("blip")  # retryable: 3 attempts, then degrade
        out = run(stubs)
        assert stubs.calls["fact_check"] == 3
        assert "Fact-checking skipped" in out["report"]


class TestCriticLoop:
    def test_weak_report_triggers_follow_up_research(self, stubs: StubAgents) -> None:
        stubs.critiques = [WEAK, GOOD]
        out = run(stubs)
        assert out["iteration"] == 2
        assert "pricing" in stubs.researched
        assert stubs.calls["write"] == 2

    def test_loop_stops_at_max_iterations(self, stubs: StubAgents) -> None:
        stubs.critiques = [WEAK]  # never satisfied
        out = run(stubs, max_iterations=2)
        assert out["iteration"] == 2
        assert stubs.calls["critique"] == 2


class TestServiceLifecycle:
    def test_human_review_pauses_and_resumes_with_subset(
        self, stubs: StubAgents, settings: Settings
    ) -> None:
        service = ResearchService(settings, stubs.agents())
        events = list(service.stream("t1", "widgets", RunOptions(human_review=True)))
        assert events[-1]["type"] == "review"
        assert service.snapshot("t1").status is RunStatus.AWAITING_REVIEW
        assert stubs.calls["research"] == 0

        events = list(service.stream("t1", decision={"sub_questions": ["costs", "risks"]}))
        assert events[-1]["type"] == "done"
        assert sorted(stubs.researched) == ["costs", "risks"]

    def test_crash_resumes_from_checkpoint_without_redoing_research(
        self, stubs: StubAgents, settings: Settings
    ) -> None:
        stubs.writer_errors = [RuntimeError("Rate limit exceeded: free-models-per-day")]
        service = ResearchService(settings, stubs.agents())
        events = list(service.stream("t2", "widgets", RunOptions(max_sub_questions=2)))
        assert events[-1] == {
            "type": "error",
            "thread_id": "t2",
            "error": "RuntimeError: Rate limit exceeded: free-models-per-day",
            "resumable": True,
        }
        assert service.snapshot("t2").status is RunStatus.INCOMPLETE

        # "Next day": a brand-new service instance on the same SQLite file.
        fresh = ResearchService(
            settings, stubs.agents(), sqlite_checkpointer(settings.checkpoint_db)
        )
        events = list(fresh.stream("t2"))
        assert events[0]["type"] == "resumed" and events[-1]["type"] == "done"
        assert stubs.calls["research"] == 2  # not re-run
        assert stubs.calls["plan"] == 1
        snap = fresh.snapshot("t2")
        assert snap.status is RunStatus.DONE and snap.report
        assert snap.plan is not None
        assert len(snap.plan.sub_questions) == 2  # options persisted with the run
        assert all(isinstance(q, SubQuestion) for q in snap.plan.sub_questions)

    def test_save_report_writes_markdown(self, stubs: StubAgents, settings: Settings) -> None:
        service = ResearchService(settings, stubs.agents())
        snap = service.run("Widgets: market & trends?", thread_id="t3")
        path = service.save_report(snap)
        assert isinstance(path, Path) and path.name.endswith("widgets-market-trends.md")
        assert path.read_text(encoding="utf-8").startswith("# Report")

    def test_finished_thread_is_not_rerun(self, stubs: StubAgents, settings: Settings) -> None:
        service = ResearchService(settings, stubs.agents())
        service.run("widgets", thread_id="t4")
        assert list(service.stream("t4")) == [{"type": "done", "thread_id": "t4"}]
        assert stubs.calls["plan"] == 1
