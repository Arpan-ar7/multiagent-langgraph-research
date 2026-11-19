"""FastAPI app end to end: background runs, SSE streaming, review, resume, errors."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from research_system.api.app import create_app
from research_system.api.client import ResearchClient, parse_sse
from research_system.config.settings import Settings
from research_system.service import ResearchService
from tests.conftest import StubAgents

pytestmark = pytest.mark.integration


@pytest.fixture
def api(stubs: StubAgents, settings: Settings) -> Iterator[ResearchClient]:
    app = create_app(ResearchService(settings, stubs.agents()))
    with TestClient(app) as http:
        yield ResearchClient(http=http)


def drain(api: ResearchClient, thread_id: str) -> list[dict]:  # type: ignore[type-arg]
    return list(api.events(thread_id))


def test_sse_parser_handles_comments_multiline_and_trailing_event() -> None:
    lines = [": ping", "event: progress", 'data: {"a":', "data: 1}", "id: 0", "", 'data: {"b": 2}']
    assert list(parse_sse(lines)) == [{"a": 1}, {"b": 2}]


def test_health_reports_version_and_providers(api: ResearchClient) -> None:
    body = api.health()
    assert body["status"] == "ok" and set(body["providers"]) == {"openrouter", "groq", "tavily"}
    assert body["defaults"]["max_sub_questions"] == 5 and body["defaults"]["human_review"] is False


def test_run_streams_progress_and_produces_report(api: ResearchClient, stubs: StubAgents) -> None:
    thread_id = api.start("How are widgets priced?", max_sub_questions=2)
    events = drain(api, thread_id)

    agents = [e["agent"] for e in events if e["type"] == "progress"]
    assert agents[0] == "planner" and "researcher" in agents and agents[-1] == "finalize"
    assert events[-1] == {"type": "done", "thread_id": thread_id}

    run = api.get(thread_id)
    assert run["status"] == "done" and not run["active"]
    assert len(run["plan"]["sub_questions"]) == 2
    assert run["critique"]["coverage"] == 5
    assert {t["node"] for t in run["timings"]} >= {"planner", "researcher", "writer", "critic"}
    assert [s["n"] for s in run["sources"]] == [1, 2]
    assert run["sources"][0]["domain"] == "example.org" and run["sources"][0]["claims"] == 1

    report = api.http.get(f"/runs/{thread_id}/report")
    assert report.status_code == 200 and report.headers["content-type"].startswith("text/markdown")
    assert "## References" in report.text


def test_events_can_be_replayed_from_last_event_id(api: ResearchClient) -> None:
    thread_id = api.start("How are widgets priced?")
    full = drain(api, thread_id)
    with api.http.stream("GET", f"/runs/{thread_id}/events", headers={"Last-Event-ID": "1"}) as r:
        replay = [e for e in parse_sse(r.iter_lines()) if e["type"] != "end"]
    assert replay == full[2:]


def test_plan_review_flow(api: ResearchClient, stubs: StubAgents) -> None:
    thread_id = api.start("How are widgets priced?", human_review=True)
    events = drain(api, thread_id)
    assert events[-1]["type"] == "review"
    assert events[-1]["sub_questions"] == ["costs", "adoption", "risks"]
    assert api.get(thread_id)["status"] == "awaiting_review"

    api.review(thread_id, ["risks"])
    events = drain(api, thread_id)
    assert events[-1]["type"] == "done"
    assert stubs.researched == ["risks"]
    assert [q["question"] for q in api.get(thread_id)["plan"]["sub_questions"]] == ["risks"]


def test_interrupted_run_can_be_resumed(api: ResearchClient, stubs: StubAgents) -> None:
    stubs.writer_errors = [RuntimeError("Rate limit exceeded: free-models-per-day")]
    thread_id = api.start("How are widgets priced?")
    first = drain(api, thread_id)
    assert first[-1]["type"] == "error" and first[-1]["resumable"] is True
    assert api.get(thread_id)["status"] == "incomplete"

    api.resume(thread_id)
    events = drain(api, thread_id)
    assert events[0]["type"] == "resumed" and events[-1]["type"] == "done"
    assert stubs.calls["research"] == 3  # research was not repeated
    full = list(api.events(thread_id, after=0))  # the whole log: both executions
    assert full[: len(first)] == first and full[len(first) :] == events


def test_error_responses(api: ResearchClient) -> None:
    http = api.http
    assert http.get("/runs/nope").status_code == 404
    assert http.post("/runs", json={"query": "hi"}).status_code == 422  # query too short
    too_many = {"query": "valid query", "options": {"max_sub_questions": 9}}
    assert http.post("/runs", json=too_many).status_code == 422

    thread_id = api.start("How are widgets priced?")
    drain(api, thread_id)
    assert http.post(f"/runs/{thread_id}/review", json={}).status_code == 409  # not paused
    assert http.post(f"/runs/{thread_id}/resume").status_code == 409  # already done
    assert http.get("/runs/nope/report").status_code == 404


def test_list_runs_newest_first(api: ResearchClient) -> None:
    first = api.start("First widget question")
    drain(api, first)
    second = api.start("Second widget question")
    drain(api, second)
    runs = api.list_runs()
    assert [r["thread_id"] for r in runs[:2]] == [second, first]
    assert runs[0]["query"] == "Second widget question" and runs[0]["status"] == "done"
