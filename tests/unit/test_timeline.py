"""UI timeline view model: folding progress events into stage / researcher states."""

from __future__ import annotations

from typing import Any

from research_system.ui.timeline import Phase, StageState, Timeline

S = StageState


def progress(agent: str, status: str, **data: Any) -> dict[str, Any]:
    return {"type": "progress", "agent": agent, "status": status, **data}


FIRST_ROUND = [
    progress("planner", "planning"),
    progress("researcher", "started", sub_question="costs"),
    progress("researcher", "started", sub_question="risks"),
    progress("researcher", "done", sub_question="costs", claims=2),
    progress("researcher", "failed", sub_question="risks"),
    progress("fact_checker", "checking", findings=1),
    progress("writer", "writing"),
    progress("critic", "reviewing"),
]


def test_first_round_states() -> None:
    t = Timeline.replay(FIRST_ROUND)
    assert t.phase is Phase.RUNNING
    assert t.stages == {
        "planner": S.DONE,
        "researcher": S.DONE,
        "fact_checker": S.DONE,
        "writer": S.DONE,
        "critic": S.RUNNING,
        "finalize": S.WAITING,
    }
    assert t.researchers == {"costs": S.DONE, "risks": S.FAILED}
    assert t.critic_passes == 1
    assert "Found 2 claims: costs" in t.log


def test_critic_follow_up_opens_a_new_round_and_resets_later_stages() -> None:
    t = Timeline.replay(
        [
            *FIRST_ROUND,
            progress("researcher", "started", sub_question="pricing"),
            progress("researcher", "started", sub_question="margins"),
        ]
    )
    assert len(t.rounds) == 2
    assert t.researchers == {"pricing": S.RUNNING, "margins": S.RUNNING}
    assert t.stages["critic"] is S.WAITING and t.stages["researcher"] is S.RUNNING
    assert t.log[-1] == "Follow-up research: margins"

    t.apply(progress("critic", "reviewing"))
    assert t.critic_passes == 2 and t.stages["researcher"] is S.DONE


def test_done_marks_every_stage_done() -> None:
    t = Timeline.replay([*FIRST_ROUND, progress("finalize", "done"), {"type": "done"}])
    assert t.phase is Phase.DONE and set(t.stages.values()) == {S.DONE}


def test_review_pause_then_resume_after_error() -> None:
    t = Timeline.replay(
        [progress("planner", "planning"), {"type": "review", "sub_questions": ["a", "b"]}]
    )
    assert t.phase is Phase.REVIEW and t.review == {"type": "review", "sub_questions": ["a", "b"]}

    t.apply(progress("writer", "writing"))
    t.apply({"type": "error", "error": "Rate limit", "resumable": True})
    assert t.phase is Phase.ERROR and t.error == "Rate limit"
    assert t.stages["writer"] is S.FAILED

    t.apply({"type": "resumed", "pending": ["writer"]})
    assert t.phase is Phase.RUNNING and t.error is None
    assert t.log[-1] == "Resumed at: writer"
