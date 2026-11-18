"""Application service: the one entry point used by the CLI (and later the API/UI).

Wraps the compiled graph + persistent checkpointer and exposes run lifecycle operations:
start, approve a paused plan, resume after a crash, inspect, and save the report.
Graph stream output is translated into simple JSON-serialisable events.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from research_system.agents import Agents, build_agents
from research_system.config.settings import Settings, get_settings
from research_system.graph import (
    RunOptions,
    build_research_graph,
    sqlite_checkpointer,
    thread_config,
)
from research_system.schemas import Critique, ResearchPlan
from research_system.utils.errors import describe
from research_system.utils.logging import configure_logging, get_logger

log = get_logger(__name__)
Event = dict[str, Any]


class RunStatus(StrEnum):
    NEW = "new"
    AWAITING_REVIEW = "awaiting_review"
    INCOMPLETE = "incomplete"  # crashed or stopped mid-run; resumable
    DONE = "done"


@dataclass
class RunSnapshot:
    """Read-only view of one research run."""

    thread_id: str
    status: RunStatus
    query: str | None = None
    plan: ResearchPlan | None = None
    report: str | None = None
    critique: Critique | None = None
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    pending: tuple[str, ...] = ()


def new_thread_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:6]


class ResearchService:
    """Runs and manages checkpointed research threads."""

    def __init__(
        self,
        settings: Settings | None = None,
        agents: Agents | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        configure_logging(self.settings.log_level)
        self.defaults = RunOptions.from_settings(self.settings)
        self.checkpointer = checkpointer or sqlite_checkpointer(self.settings.checkpoint_db)
        self.graph = build_research_graph(
            agents or build_agents(self.settings), self.defaults, self.checkpointer
        )

    # ------------------------------------------------------------------ inspection
    def snapshot(self, thread_id: str) -> RunSnapshot:
        snap = self.graph.get_state(thread_config(thread_id))
        values = snap.values or {}
        if snap.interrupts:
            status = RunStatus.AWAITING_REVIEW
        elif snap.next:
            status = RunStatus.INCOMPLETE
        elif values.get("report"):
            status = RunStatus.DONE
        else:
            status = RunStatus.NEW
        return RunSnapshot(
            thread_id=thread_id,
            status=status,
            query=values.get("query"),
            plan=values.get("plan"),
            report=values.get("report"),
            critique=values.get("critique"),
            failures=values.get("failures", []),
            warnings=values.get("warnings", []),
            metrics=values.get("metrics", []),
            pending=tuple(snap.next),
        )

    # ------------------------------------------------------------------ execution
    def stream(
        self,
        thread_id: str,
        query: str | None = None,
        options: RunOptions | None = None,
        decision: dict[str, Any] | None = None,
    ) -> Iterator[Event]:
        """Advance a run from wherever it is and yield progress events.

        - new thread: starts with `query` (and `options`)
        - paused for review: resumes with `decision` (e.g. {"sub_questions": [...]})
        - incomplete (crash/quota): resumes at the failed node; finished steps are not repeated
        """
        current = self.snapshot(thread_id)
        payload: Any
        if current.status is RunStatus.AWAITING_REVIEW:
            payload = Command(resume=decision or {})
        elif current.status is RunStatus.INCOMPLETE:
            yield {"type": "resumed", "pending": list(current.pending)}
            payload = None
        elif current.status is RunStatus.DONE:
            yield {"type": "done", "thread_id": thread_id}
            return
        else:
            if not query:
                raise ValueError("A query is required to start a new run.")
            payload = {"query": query, "options": (options or self.defaults).model_dump()}

        try:
            for mode, chunk in self.graph.stream(
                payload, thread_config(thread_id), stream_mode=["custom", "updates"]
            ):
                data = cast(dict[str, Any], chunk)
                if mode == "custom":
                    yield {"type": "progress", **data}
                elif "__interrupt__" in data:
                    yield {
                        "type": "review",
                        "thread_id": thread_id,
                        **data["__interrupt__"][0].value,
                    }
        except Exception as e:
            log.error("run_stopped", thread_id=thread_id, error=describe(e))
            yield {
                "type": "error",
                "thread_id": thread_id,
                "error": describe(e, 300),
                "resumable": True,
            }
            return

        final = self.snapshot(thread_id)
        if final.status is RunStatus.DONE:
            yield {"type": "done", "thread_id": thread_id}

    def run(
        self, query: str, options: RunOptions | None = None, thread_id: str | None = None
    ) -> RunSnapshot:
        """Blocking convenience: run to completion (or to a review pause / error)."""
        thread_id = thread_id or new_thread_id()
        for _ in self.stream(thread_id, query, options):
            pass
        return self.snapshot(thread_id)

    # ------------------------------------------------------------------ output
    def save_report(self, snapshot: RunSnapshot) -> Path:
        """Write the report to `reports/<date>-<slug>.md` and return the path."""
        if not snapshot.report:
            raise ValueError("Run has no report yet.")
        slug = re.sub(r"[^a-z0-9]+", "-", (snapshot.query or "report").lower()).strip("-")[:60]
        path = self.settings.reports_dir / f"{datetime.now():%Y%m%d}-{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(snapshot.report, encoding="utf-8")
        return path
