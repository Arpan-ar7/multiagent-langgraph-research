"""Evaluation CLI.

uv run research-eval --dry-run                 # verify the pipeline, no API calls
uv run research-eval --max-runs 2              # real runs; fits the free daily quota
uv run research-eval --questions 3 --configs single_pass critic_loop
uv run research-eval --summary                 # just print the results table
"""

from __future__ import annotations

import argparse
import sys

from research_system.config.settings import get_settings
from research_system.evals.dataset import EVAL_QUESTIONS
from research_system.evals.report import markdown_table
from research_system.evals.runner import DEFAULT_CONFIGS, build_runner, load_results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="research-eval", description="Evaluate the research system")
    p.add_argument("--dry-run", action="store_true", help="stub agents and judge (free)")
    p.add_argument(
        "--questions", type=int, default=3, help=f"number of questions (max {len(EVAL_QUESTIONS)})"
    )
    p.add_argument(
        "--configs",
        nargs="+",
        default=[c.name for c in DEFAULT_CONFIGS],
        choices=[c.name for c in DEFAULT_CONFIGS],
    )
    p.add_argument(
        "--max-runs", type=int, help="max (config, question) pairs to attempt this session"
    )
    p.add_argument(
        "--no-langsmith", action="store_true", help="do not sync dataset / send feedback"
    )
    p.add_argument("--summary", action="store_true", help="only print the results table")
    args = p.parse_args(argv)

    settings = get_settings()
    name = "eval_results_dryrun.jsonl" if args.dry_run else "eval_results.jsonl"
    results_path = settings.data_dir / name

    if not args.summary:
        runner = build_runner(
            args.dry_run, results_path, use_langsmith=not args.no_langsmith, settings=settings
        )
        if runner.langsmith is not None:
            from research_system.evals.dataset import sync_langsmith_dataset

            dataset_id = sync_langsmith_dataset(runner.langsmith, EVAL_QUESTIONS[: args.questions])
            print(f"LangSmith dataset synced ({dataset_id})")
        configs = [c for c in DEFAULT_CONFIGS if c.name in args.configs]
        outcome = runner.run(configs, EVAL_QUESTIONS[: args.questions], args.max_runs)
        for row in outcome.completed:
            print(
                f"  done  {row['config']:<12} {row['kind']:<11} judge="
                f"{row['relevance']}/{row['completeness']}/{row['specificity']} "
                f"grounding={row['grounding_rate']:.2f} calls={row['llm_calls_last_session']}"
            )
        print(f"completed {len(outcome.completed)}, already done {outcome.skipped}")
        if outcome.stopped_reason:
            print(f"stopped: {outcome.stopped_reason}")

    title = (
        "Evaluation results (DRY RUN: stub agents, not real results)"
        if args.dry_run
        else "Evaluation results"
    )
    table = markdown_table(load_results(results_path), title)
    print("\n" + table)
    if not args.dry_run:
        out = settings.reports_dir / "evaluation.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(table, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
