"""Folds a run's progress events into a view model for the UI (no Streamlit import, so testable).

Events come from `ResearchService.stream` via the API's SSE endpoint:
    {"type": "progress", "agent": ..., "status": ..., ...}   one agent step
    {"type": "review", "objective": ..., "sub_questions": [...]}   paused for plan approval
    {"type": "resumed", "pending": [...]}   an interrupted run continues
    {"type": "error", "error": ..., "resumable": bool}
    {"type": "done", "thread_id": ...}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

STAGES: dict[str, str] = {
    "planner": "Planner",
    "researcher": "Researchers",
    "fact_checker": "Fact-checker",
    "writer": "Writer",
    "critic": "Critic",
    "finalize": "Finalize",
}


class StageState(StrEnum):
    WAITING = "waiting"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Phase(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    REVIEW = "review"
    ERROR = "error"
    DONE = "done"


@dataclass
class Timeline:
    """Current picture of a run, rebuilt by replaying its events in order."""

    phase: Phase = Phase.IDLE
    stages: dict[str, StageState] = field(
        default_factory=lambda: dict.fromkeys(STAGES, StageState.WAITING)
    )
    rounds: list[dict[str, StageState]] = field(default_factory=list)  # sub_question -> state
    critic_passes: int = 0
    log: list[str] = field(default_factory=list)
    error: str | None = None
    review: dict[str, Any] | None = None

    @classmethod
    def replay(cls, events: list[dict[str, Any]]) -> Timeline:
        timeline = cls()
        for event in events:
            timeline.apply(event)
        return timeline

    @property
    def researchers(self) -> dict[str, StageState]:
        """Researchers of the latest round (the first round, or a critic follow-up round)."""
        return self.rounds[-1] if self.rounds else {}

    def apply(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "progress":
            self.phase = Phase.RUNNING
            self._progress(event)
        elif kind == "review":
            self.phase = Phase.REVIEW
            self.review = event
            count = len(event.get("sub_questions", []))
            self.log.append(f"Plan ready: {count} sub-questions, waiting for approval")
        elif kind == "resumed":
            self.phase, self.error = Phase.RUNNING, None
            self.log.append(f"Resumed at: {', '.join(event.get('pending', [])) or 'next step'}")
        elif kind == "error":
            self.phase, self.error = Phase.ERROR, str(event.get("error", "unknown error"))
            for stage, state in self.stages.items():
                if state is StageState.RUNNING:
                    self.stages[stage] = StageState.FAILED
            self.log.append(f"Stopped: {self.error}")
        elif kind == "done":
            self.phase = Phase.DONE
            self.stages = dict.fromkeys(STAGES, StageState.DONE)
            self.log.append("Report ready")

    # ------------------------------------------------------------------ internals
    def _progress(self, event: dict[str, Any]) -> None:
        agent, status = str(event.get("agent")), str(event.get("status"))
        if agent == "researcher":
            self._researcher(str(event.get("sub_question", "?")), status, event)
            return
        self._finish_earlier(agent)
        if agent == "critic":
            self.critic_passes += 1
        self.stages[agent] = StageState.DONE if agent == "finalize" else StageState.RUNNING
        self.log.append(_describe(agent, status, event, self.critic_passes))

    def _researcher(self, question: str, status: str, event: dict[str, Any]) -> None:
        if status == "started":
            # The first researcher, or one starting after the critic ran, opens a new round;
            # the later stages then wait for that round to finish.
            if not self.rounds or self.stages["critic"] is not StageState.WAITING:
                self.rounds.append({})
                for stage in ("fact_checker", "writer", "critic"):
                    self.stages[stage] = StageState.WAITING
            self._finish_earlier("researcher")
            self.stages["researcher"] = StageState.RUNNING
            self.rounds[-1][question] = StageState.RUNNING
            label = "Follow-up research" if len(self.rounds) > 1 else "Researching"
            self.log.append(f"{label}: {question}")
        elif status == "done":
            self._set_researcher(question, StageState.DONE)
            self.log.append(f"Found {event.get('claims', 0)} claims: {question}")
        elif status == "failed":
            self._set_researcher(question, StageState.FAILED)
            self.log.append(f"Research failed: {question}")

    def _set_researcher(self, question: str, state: StageState) -> None:
        if not self.rounds:
            self.rounds.append({})
        self.rounds[-1][question] = state

    def _finish_earlier(self, agent: str) -> None:
        """Mark every running stage before `agent` as done (the graph only moves forward)."""
        order = list(STAGES)
        for stage in order[: order.index(agent)] if agent in order else []:
            if self.stages[stage] is StageState.RUNNING:
                self.stages[stage] = StageState.DONE


def _describe(agent: str, status: str, event: dict[str, Any], critic_passes: int) -> str:
    match agent:
        case "planner":
            return "Planning sub-questions"
        case "fact_checker":
            return f"Fact-checking claims from {event.get('findings', 0)} findings"
        case "writer":
            return "Writing the report"
        case "critic":
            return f"Reviewing the draft (pass {critic_passes})"
        case "finalize":
            problems = int(event.get("citation_problems", 0))
            return "Finalizing" + (f" ({problems} citation issues noted)" if problems else "")
    return f"{agent}: {status}"
