"""Budget-aware, resumable evaluation runner.

- Each (config, question) pair runs on a stable, checkpointed thread id, so a run stopped by
  an exhausted quota continues mid-graph next time instead of starting over.
- Every finished pair is appended to a JSONL file immediately; finished pairs are skipped.
- `max_runs` limits how many pairs one invocation attempts (fit the daily quota).
- With LangSmith enabled, each evaluated run's trace receives the scores as feedback, so
  configurations can be compared in the LangSmith UI.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from research_system.config.llm import LLMFactory
from research_system.config.settings import Settings, get_settings
from research_system.evals.dataset import EVAL_QUESTIONS, EvalQuestion
from research_system.evals.metrics import Judge, JudgeScore, UsageCounter, report_metrics
from research_system.graph import RunOptions
from research_system.service import ResearchService, RunStatus
from research_system.utils.errors import describe
from research_system.utils.logging import get_logger

log = get_logger(__name__)
JudgeFn = Callable[[str, str], JudgeScore]


@dataclass(frozen=True)
class EvalConfig:
    name: str
    options: RunOptions


DEFAULT_CONFIGS: tuple[EvalConfig, ...] = (
    EvalConfig("single_pass", RunOptions(max_sub_questions=3, max_tool_calls=3, max_iterations=1)),
    EvalConfig("critic_loop", RunOptions(max_sub_questions=3, max_tool_calls=3, max_iterations=2)),
)

JUDGE_KEYS = ("relevance", "completeness", "specificity")


def thread_id_for(config: EvalConfig, question: EvalQuestion) -> str:
    digest = hashlib.sha1(question.question.encode()).hexdigest()[:10]
    return f"eval-{config.name}-{digest}"


def load_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


@dataclass
class EvalOutcome:
    completed: list[dict[str, Any]] = field(default_factory=list)
    skipped: int = 0
    stopped_reason: str | None = None


class EvalRunner:
    """Runs configurations x questions through the real service and records results."""

    def __init__(
        self,
        service: ResearchService,
        judge: JudgeFn,
        results_path: Path,
        langsmith_client: Any | None = None,
    ) -> None:
        self.service = service
        self.judge = judge
        self.results_path = results_path
        self.langsmith = langsmith_client

    def run(
        self,
        configs: Iterable[EvalConfig] = DEFAULT_CONFIGS,
        questions: Iterable[EvalQuestion] = EVAL_QUESTIONS,
        max_runs: int | None = None,
    ) -> EvalOutcome:
        done = {(r["config"], r["question"]) for r in load_results(self.results_path)}
        outcome = EvalOutcome()
        attempted = 0
        for question in questions:  # question-major order: both configs of a question run together
            for config in configs:
                if (config.name, question.question) in done:
                    outcome.skipped += 1
                    continue
                if max_runs is not None and attempted >= max_runs:
                    outcome.stopped_reason = f"max_runs={max_runs} reached"
                    return outcome
                attempted += 1
                row = self._run_one(config, question)
                if row is None:
                    outcome.stopped_reason = "run stopped (likely quota); re-run later to resume"
                    return outcome
                self._append(row)
                outcome.completed.append(row)
        return outcome

    # ------------------------------------------------------------------ internals
    def _run_one(self, config: EvalConfig, question: EvalQuestion) -> dict[str, Any] | None:
        thread_id = thread_id_for(config, question)
        counter = UsageCounter()
        run_id = uuid4()
        extra = {
            "callbacks": [counter],
            "run_id": run_id,
            "run_name": f"eval:{config.name}",
            "tags": ["eval", config.name, question.kind],
            "metadata": {"eval_config": config.name, "question_kind": question.kind},
        }
        log.info("eval_run_start", config=config.name, kind=question.kind, thread_id=thread_id)
        t0 = time.perf_counter()
        for event in self.service.stream(
            thread_id, question.question, config.options, config_extra=extra
        ):
            if event["type"] == "error":
                log.warning("eval_run_stopped", config=config.name, error=event["error"])
                return None
        snapshot = self.service.snapshot(thread_id)
        if snapshot.status is not RunStatus.DONE or not snapshot.report:
            return None

        values = self.service.graph.get_state({"configurable": {"thread_id": thread_id}}).values
        try:
            score = self.judge(question.question, snapshot.report)
        except Exception as e:
            log.warning("eval_judge_failed", error=describe(e))
            return None  # leave the pair unrecorded; the finished run is reused next time

        row: dict[str, Any] = {
            "config": config.name,
            "kind": question.kind,
            "question": question.question,
            "thread_id": thread_id,
            "run_id": str(run_id),
            "seconds_last_session": round(time.perf_counter() - t0, 1),
            "llm_calls_last_session": counter.calls,
            "tokens_last_session": counter.tokens,
            **report_metrics(values),
            **score.model_dump(),
        }
        self._send_feedback(run_id, row, score)
        return row

    def _append(self, row: dict[str, Any]) -> None:
        self.results_path.parent.mkdir(parents=True, exist_ok=True)
        with self.results_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def _send_feedback(self, run_id: Any, row: dict[str, Any], score: JudgeScore) -> None:
        if self.langsmith is None:
            return
        try:
            from langchain_core.tracers.langchain import wait_for_all_tracers

            wait_for_all_tracers()  # make sure the run exists in LangSmith before scoring it
            for key in JUDGE_KEYS:
                self.langsmith.create_feedback(
                    run_id, key=key, score=getattr(score, key) / 5, comment=score.rationale
                )
            for key in ("grounding_rate", "citation_problems", "critic_iterations"):
                self.langsmith.create_feedback(run_id, key=key, score=row[key])
        except Exception as e:  # feedback is best-effort; local results are the source of truth
            log.warning("langsmith_feedback_failed", error=describe(e))


def build_runner(
    dry_run: bool,
    results_path: Path,
    use_langsmith: bool,
    settings: Settings | None = None,
) -> EvalRunner:
    """Wire a runner for real or dry-run evaluation."""
    settings = settings or get_settings()
    if dry_run:
        from research_system.evals.stubs import dry_run_agents, dry_run_judge

        os.environ["LANGSMITH_TRACING"] = "false"  # never upload fake runs
        # Separate checkpoint DB: dry-run threads must never be mistaken for real finished runs.
        isolated = settings.model_copy(
            update={"checkpoint_db": settings.data_dir / "checkpoints-dryrun.sqlite"}
        )
        service = ResearchService(isolated, dry_run_agents())
        return EvalRunner(service, dry_run_judge, results_path)

    client = None
    if use_langsmith and os.getenv("LANGSMITH_API_KEY"):
        from langsmith import Client

        client = Client()
    return EvalRunner(ResearchService(settings), Judge(LLMFactory(settings)), results_path, client)
