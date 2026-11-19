"""Evaluation package: metrics, runner resumability/budget, LangSmith integration (faked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from research_system.config.settings import Settings
from research_system.evals import (
    DEFAULT_CONFIGS,
    EVAL_QUESTIONS,
    EvalRunner,
    JudgeScore,
    markdown_table,
    report_metrics,
    summarize,
    sync_langsmith_dataset,
)
from research_system.evals.runner import load_results, thread_id_for
from research_system.evals.stubs import dry_run_agents, dry_run_judge
from research_system.graph import RunOptions
from research_system.service import ResearchService
from tests.conftest import StubAgents

QUESTIONS = EVAL_QUESTIONS[:2]


class FakeLangSmith:
    def __init__(self) -> None:
        self.feedback: list[dict[str, Any]] = []
        self.examples: list[SimpleNamespace] = []
        self.dataset = SimpleNamespace(id=uuid4())
        self.created = False
        self.project_id = uuid4()

    def read_run(self, run_id: Any) -> SimpleNamespace:
        return SimpleNamespace(id=run_id, session_id=self.project_id)

    def create_feedback(self, run_id: Any, **kw: Any) -> None:
        self.feedback.append({"run_id": run_id, **kw})

    def has_dataset(self, dataset_name: str) -> bool:
        return self.created

    def create_dataset(self, dataset_name: str, description: str) -> SimpleNamespace:
        self.created = True
        return self.dataset

    def read_dataset(self, dataset_name: str) -> SimpleNamespace:
        return self.dataset

    def list_examples(self, dataset_id: Any) -> list[SimpleNamespace]:
        return self.examples

    def create_examples(self, dataset_id: Any, examples: list[dict[str, Any]]) -> None:
        self.examples += [SimpleNamespace(inputs=e["inputs"]) for e in examples]


def make_runner(settings: Settings, client: Any = None, judge: Any = dry_run_judge) -> EvalRunner:
    service = ResearchService(settings, dry_run_agents())
    return EvalRunner(service, judge, settings.data_dir / "results.jsonl", client)


def test_report_metrics_from_finished_run(stubs: StubAgents, settings: Settings) -> None:
    service = ResearchService(settings, stubs.agents())
    service.run("widgets", thread_id="m1")
    values = service.graph.get_state({"configurable": {"thread_id": "m1"}}).values
    m = report_metrics(values)
    assert m["claims"] == 3 and m["grounding_rate"] == 1.0
    assert m["sources_cited"] == 3 and m["citation_problems"] == 0
    assert m["critic_iterations"] == 1 and m["critic_min_score"] == 5


def test_runner_records_results_and_counts_llm_calls(settings: Settings) -> None:
    outcome = make_runner(settings).run(DEFAULT_CONFIGS, QUESTIONS)
    assert len(outcome.completed) == 4 and outcome.stopped_reason is None
    rows = load_results(settings.data_dir / "results.jsonl")
    assert {(r["config"], r["kind"]) for r in rows} == {
        (c.name, q.kind) for c in DEFAULT_CONFIGS for q in QUESTIONS
    }
    single = [r for r in rows if r["config"] == "single_pass"]
    assert all(
        r["llm_calls_last_session"] == 7 for r in single
    )  # plan + 3 research + fc + write + critic
    assert all(r["critic_iterations"] == 1 for r in single)


def test_runner_is_resumable_and_respects_budget(settings: Settings) -> None:
    first = make_runner(settings).run(DEFAULT_CONFIGS, QUESTIONS, max_runs=1)
    assert len(first.completed) == 1 and first.stopped_reason == "max_runs=1 reached"
    second = make_runner(settings).run(DEFAULT_CONFIGS, QUESTIONS)
    assert second.skipped == 1 and len(second.completed) == 3


def test_runner_stops_without_recording_when_judge_fails(settings: Settings) -> None:
    def failing_judge(question: str, report: str) -> JudgeScore:
        raise RuntimeError("Rate limit exceeded: free-models-per-day")

    outcome = make_runner(settings, judge=failing_judge).run(DEFAULT_CONFIGS, QUESTIONS)
    assert outcome.completed == [] and "quota" in (outcome.stopped_reason or "")
    assert load_results(settings.data_dir / "results.jsonl") == []
    # The finished graph run is reused next time (only judging is repeated).
    service = make_runner(settings).service
    assert service.snapshot(thread_id_for(DEFAULT_CONFIGS[0], QUESTIONS[0])).report


def test_feedback_is_attached_to_the_traced_run(settings: Settings) -> None:
    client = FakeLangSmith()
    outcome = make_runner(settings, client).run(DEFAULT_CONFIGS[:1], QUESTIONS[:1])
    run_id = outcome.completed[0]["run_id"]
    keys = {f["key"] for f in client.feedback}
    assert keys == {
        "relevance",
        "completeness",
        "specificity",
        "grounding_rate",
        "citation_problems",
        "critic_iterations",
    }
    assert all(str(f["run_id"]) == run_id for f in client.feedback)
    # Newer LangSmith SDKs require the project (session) and trace on each feedback call.
    assert all(f["session_id"] == client.project_id for f in client.feedback)
    assert all(str(f["trace_id"]) == run_id for f in client.feedback)
    assert all(0 < f["score"] <= 1 for f in client.feedback if f["key"] == "relevance")


def test_dataset_sync_is_idempotent() -> None:
    client = FakeLangSmith()
    first = sync_langsmith_dataset(client)
    second = sync_langsmith_dataset(client)
    assert first == second and len(client.examples) == len(EVAL_QUESTIONS)


def test_summary_table() -> None:
    base = {
        k: 1
        for k in (
            "relevance",
            "completeness",
            "specificity",
            "grounding_rate",
            "citation_problems",
            "sources_cited",
            "distinct_domains",
            "critic_iterations",
            "failed_researchers",
            "words",
        )
    }
    rows = [
        {"config": "a", **base},
        {"config": "a", **base, "relevance": 3},
        {"config": "b", **base},
    ]
    summary = summarize(rows)
    assert summary["a"]["relevance"] == 2 and summary["a"]["n"] == 2
    table = markdown_table(rows)
    assert "| Judge: relevance (1-5) | 2 | 1 |" in table
    assert markdown_table([]).endswith("No results yet.\n")


def test_thread_ids_are_stable_and_config_specific() -> None:
    q = EVAL_QUESTIONS[0]
    a, b = DEFAULT_CONFIGS
    assert thread_id_for(a, q) == thread_id_for(a, q) != thread_id_for(b, q)


@pytest.mark.parametrize("config", DEFAULT_CONFIGS)
def test_default_configs_are_valid_run_options(config: Any) -> None:
    assert isinstance(config.options, RunOptions)
    assert isinstance(Path(".") / thread_id_for(config, EVAL_QUESTIONS[0]), Path)
