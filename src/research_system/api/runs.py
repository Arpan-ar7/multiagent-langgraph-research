"""Background execution of research runs, decoupled from HTTP connections.

Each run executes in a worker thread that appends events to an in-memory log. HTTP clients
read the log (SSE) from any position, so a disconnected browser does not stop the run and
several viewers can follow the same run. Progress itself is checkpointed by the service,
so even a server restart only loses the event log, not the run.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from research_system.graph import RunOptions
from research_system.service import Event, ResearchService, RunStatus, new_thread_id
from research_system.utils.errors import describe
from research_system.utils.logging import get_logger

log = get_logger(__name__)


class RunConflictError(Exception):
    """The requested action is not valid for the run's current state."""


class RunNotFoundError(Exception):
    """No run exists with that id."""


@dataclass
class RunJob:
    """Event log of one run's executions (start, then each resume)."""

    thread_id: str
    events: list[Event] = field(default_factory=list)
    active: bool = False
    _cond: threading.Condition = field(default_factory=threading.Condition)

    def append(self, event: Event) -> None:
        with self._cond:
            self.events.append(event)
            self._cond.notify_all()

    def set_active(self, active: bool) -> None:
        with self._cond:
            self.active = active
            self._cond.notify_all()

    def wait(self, after: int, timeout: float) -> tuple[list[Event], bool]:
        """Events with index >= `after`, waiting up to `timeout`; also returns `active`."""
        with self._cond:
            if len(self.events) <= after and self.active:
                self._cond.wait(timeout)
            return self.events[after:], self.active


class RunManager:
    """Starts, resumes and tracks runs; one worker thread per active run."""

    def __init__(self, service: ResearchService) -> None:
        self.service = service
        self._jobs: dict[str, RunJob] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ commands
    def start(self, query: str, options: RunOptions) -> str:
        thread_id = new_thread_id()
        self._launch(thread_id, query=query, options=options)
        return thread_id

    def submit_review(self, thread_id: str, sub_questions: list[str] | None) -> None:
        if self.service.snapshot(thread_id).status is not RunStatus.AWAITING_REVIEW:
            raise RunConflictError("Run is not waiting for plan review.")
        decision = {"sub_questions": sub_questions} if sub_questions else {}
        self._launch(thread_id, decision=decision)

    def resume(self, thread_id: str) -> None:
        status = self.status(thread_id)
        if status is not RunStatus.INCOMPLETE:
            raise RunConflictError(f"Only incomplete runs can be resumed (run is {status.value}).")
        self._launch(thread_id)

    # ------------------------------------------------------------------ queries
    def status(self, thread_id: str) -> RunStatus:
        status = self.service.snapshot(thread_id).status
        if status is RunStatus.NEW and thread_id not in self._jobs:
            raise RunNotFoundError(thread_id)
        return status

    def is_active(self, thread_id: str) -> bool:
        job = self._jobs.get(thread_id)
        return bool(job and job.active)

    def follow(
        self, thread_id: str, after: int = 0, poll_s: float = 15.0
    ) -> Iterator[tuple[int, Event]]:
        """Yield (index, event) from `after` until the run's current execution ends.

        Yields `(-1, {})` heartbeats while waiting, so callers can check for disconnects.
        """
        job = self._jobs.get(thread_id)
        if job is None:
            return
        position = after
        while True:
            events, active = job.wait(position, poll_s)
            for event in events:
                yield position, event
                position += 1
            if not active and position >= len(job.events):
                return
            if not events:
                yield -1, {}

    # ------------------------------------------------------------------ internals
    def _launch(self, thread_id: str, **stream_kwargs: Any) -> None:
        with self._lock:
            job = self._jobs.setdefault(thread_id, RunJob(thread_id))
            if job.active:
                raise RunConflictError("Run is already executing.")
            job.set_active(True)
        worker = threading.Thread(
            target=self._execute, args=(job, stream_kwargs), name=f"run-{thread_id}", daemon=True
        )
        worker.start()

    def _execute(self, job: RunJob, stream_kwargs: dict[str, Any]) -> None:
        try:
            for event in self.service.stream(job.thread_id, **stream_kwargs):
                job.append(event)
        except Exception as e:  # service.stream already converts graph errors; this is a backstop
            log.error("run_worker_crashed", thread_id=job.thread_id, error=describe(e))
            job.append({"type": "error", "error": describe(e), "resumable": True})
        finally:
            job.set_active(False)
