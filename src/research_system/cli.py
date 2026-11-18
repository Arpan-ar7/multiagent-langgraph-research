"""Command-line interface.

Examples:
    uv run research "How are AI coding agents changing software engineering?"
    uv run research "..." --sub-questions 3 --iterations 1 --review
    uv run research --resume 20261119-101500-ab12cd      # continue a paused or crashed run
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from research_system import __version__


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="research", description="Multi-agent AI research system")
    p.add_argument("query", nargs="?", help="research question")
    p.add_argument("--resume", metavar="THREAD_ID", help="resume a paused or interrupted run")
    p.add_argument(
        "--sub-questions", type=int, help="max sub-questions / parallel researchers (1-5)"
    )
    p.add_argument("--iterations", type=int, help="max critic iterations (1 = no revision loop)")
    p.add_argument("--tool-calls", type=int, help="max tool calls per researcher")
    p.add_argument("--review", action="store_true", help="approve or edit the plan before research")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)
    if not args.query and not args.resume:
        p.error("give a query, or --resume THREAD_ID")
    return args


def _ask_review(event: dict[str, Any]) -> dict[str, Any]:
    """Terminal plan approval: keep all sub-questions or pick a subset by number."""
    print(f"\nObjective: {event['objective']}\nProposed sub-questions:")
    questions: list[str] = event["sub_questions"]
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q}")
    answer = input("Keep which? (e.g. 1,3; Enter = all): ").strip()
    if not answer:
        return {}
    picked = [questions[int(n) - 1] for n in answer.replace(" ", "").split(",") if n.isdigit()]
    return {"sub_questions": [q for q in picked if q]}


def _print_progress(event: dict[str, Any]) -> None:
    detail = f": {event['sub_question'][:80]}" if "sub_question" in event else ""
    print(f"  [{event['agent']}] {event['status']}{detail}", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    from research_system.graph import RunOptions
    from research_system.service import ResearchService, RunStatus, new_thread_id

    service = ResearchService()
    options = RunOptions.from_settings(
        service.settings,
        max_sub_questions=args.sub_questions,
        max_iterations=args.iterations,
        max_tool_calls=args.tool_calls,
        human_review=True if args.review else None,
    )
    thread_id = args.resume or new_thread_id()
    print(f"Run: {thread_id}")

    decision: dict[str, Any] | None = None
    query = args.query
    while True:
        review_event = None
        for event in service.stream(thread_id, query, options, decision):
            if event["type"] == "progress":
                _print_progress(event)
            elif event["type"] == "resumed":
                print(f"  resuming at {event['pending']}")
            elif event["type"] == "review":
                review_event = event
            elif event["type"] == "error":
                print(f"\nRun stopped: {event['error']}")
                print(f"Resume later with:  uv run research --resume {thread_id}")
                return 1
        if review_event is None:
            break
        decision, query = _ask_review(review_event), None

    snapshot = service.snapshot(thread_id)
    if snapshot.status is not RunStatus.DONE:
        print(f"Run is {snapshot.status.value}. Resume with: uv run research --resume {thread_id}")
        return 1
    path = service.save_report(snapshot)
    critique = snapshot.critique
    if critique:
        print(
            f"\nCritic scores: coverage={critique.coverage} evidence={critique.evidence_use} "
            f"coherence={critique.coherence}"
        )
    print(f"Report saved to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
