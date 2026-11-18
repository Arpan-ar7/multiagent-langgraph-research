"""Evaluation: benchmark questions, metrics, LLM-as-judge, resumable runner, reporting."""

from research_system.evals.dataset import EVAL_QUESTIONS, EvalQuestion, sync_langsmith_dataset
from research_system.evals.metrics import Judge, JudgeScore, UsageCounter, report_metrics
from research_system.evals.report import markdown_table, summarize
from research_system.evals.runner import DEFAULT_CONFIGS, EvalConfig, EvalRunner, build_runner

__all__ = [
    "DEFAULT_CONFIGS",
    "EVAL_QUESTIONS",
    "EvalConfig",
    "EvalQuestion",
    "EvalRunner",
    "Judge",
    "JudgeScore",
    "UsageCounter",
    "build_runner",
    "markdown_table",
    "report_metrics",
    "summarize",
    "sync_langsmith_dataset",
]
