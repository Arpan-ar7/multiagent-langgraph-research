"""FastAPI application.

Endpoints
    GET  /health                    liveness + which providers are configured
    POST /runs                      start a run (202) -> thread_id
    GET  /runs                      recent runs
    GET  /runs/{id}                 run state (plan, critique, report, timings)
    GET  /runs/{id}/events          live progress (Server-Sent Events, resumable: Last-Event-ID)
    POST /runs/{id}/review          approve / narrow the plan of a paused run
    POST /runs/{id}/resume          continue an interrupted run (e.g. after a quota stop)
    GET  /runs/{id}/report          final report as text/markdown

Run with:  uv run research-api   (then open http://127.0.0.1:8000/docs)
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sse_starlette import EventSourceResponse, ServerSentEvent

from research_system import __version__
from research_system.api.runs import RunConflictError, RunManager, RunNotFoundError
from research_system.api.schemas import (
    Health,
    ReviewRequest,
    RunCreated,
    RunSummary,
    RunView,
    StartRunRequest,
)
from research_system.graph import RunOptions
from research_system.service import ResearchService


def get_manager(request: Request) -> RunManager:
    """Dependency: the app's RunManager (module-level so FastAPI can resolve annotations)."""
    return request.app.state.manager  # type: ignore[no-any-return]


Manager = Annotated[RunManager, Depends(get_manager)]


def create_app(service: ResearchService | None = None) -> FastAPI:
    """App factory; pass a service (e.g. with stub agents) for tests."""
    app = FastAPI(
        title="Multi-Agent Research System",
        version=__version__,
        description="LangGraph multi-agent research: plan, research, fact-check, write, critique.",
    )
    app.state.manager = RunManager(service or ResearchService())

    def view(m: RunManager, thread_id: str, include_report: bool = True) -> RunView:
        try:
            m.status(thread_id)
        except RunNotFoundError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found") from None
        return RunView.from_snapshot(
            m.service.snapshot(thread_id), m.is_active(thread_id), include_report
        )

    @app.get("/health", response_model=Health)
    def health(m: Manager) -> Health:
        s = m.service.settings
        providers = {
            "openrouter": bool(s.openrouter_api_key),
            "groq": bool(s.groq_api_key),
            "tavily": bool(s.tavily_api_key),
        }
        return Health(
            version=__version__, providers=providers, defaults=m.service.defaults.model_dump()
        )

    @app.post("/runs", response_model=RunCreated, status_code=status.HTTP_202_ACCEPTED)
    def start_run(body: StartRunRequest, m: Manager) -> RunCreated:
        options = RunOptions.from_settings(m.service.settings, **body.options.model_dump())
        thread_id = m.start(body.query, options)
        return RunCreated(thread_id=thread_id, events_url=f"/runs/{thread_id}/events")

    @app.get("/runs", response_model=list[RunSummary])
    def list_runs(m: Manager, limit: int = 20) -> list[RunSummary]:
        return [
            RunSummary(thread_id=s.thread_id, status=s.status.value, query=s.query)
            for s in m.service.list_runs(limit)
        ]

    @app.get("/runs/{thread_id}", response_model=RunView)
    def get_run(thread_id: str, m: Manager, include_report: bool = True) -> RunView:
        return view(m, thread_id, include_report)

    @app.get("/runs/{thread_id}/report", response_class=PlainTextResponse)
    def get_report(thread_id: str, m: Manager) -> PlainTextResponse:
        report = view(m, thread_id).report
        if not report:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not ready")
        return PlainTextResponse(report, media_type="text/markdown; charset=utf-8")

    @app.post(
        "/runs/{thread_id}/review", response_model=RunView, status_code=status.HTTP_202_ACCEPTED
    )
    def review(thread_id: str, body: ReviewRequest, m: Manager) -> RunView:
        view(m, thread_id)  # 404 check
        try:
            m.submit_review(thread_id, body.sub_questions)
        except RunConflictError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
        return view(m, thread_id, include_report=False)

    @app.post(
        "/runs/{thread_id}/resume", response_model=RunView, status_code=status.HTTP_202_ACCEPTED
    )
    def resume(thread_id: str, m: Manager) -> RunView:
        view(m, thread_id)
        try:
            m.resume(thread_id)
        except RunConflictError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
        return view(m, thread_id, include_report=False)

    @app.get("/runs/{thread_id}/events")
    async def events(
        thread_id: str,
        request: Request,
        m: Manager,
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> EventSourceResponse:
        view(m, thread_id, include_report=False)
        after = int(last_event_id) + 1 if last_event_id and last_event_id.isdigit() else 0

        async def stream() -> AsyncIterator[ServerSentEvent]:
            follower = m.follow(thread_id, after, poll_s=1.0)
            while True:
                item = await asyncio.to_thread(next, follower, None)
                if item is None or await request.is_disconnected():
                    break
                index, event = item
                if index < 0:
                    continue  # heartbeat: loop again so disconnects are noticed
                yield ServerSentEvent(data=json.dumps(event), event=event["type"], id=str(index))
            yield ServerSentEvent(data=json.dumps({"type": "end"}), event="end")

        return EventSourceResponse(stream(), ping=15)

    return app


def run() -> None:
    """Console entry point: `uv run research-api` (bind with RS_API_HOST / RS_API_PORT)."""
    import os

    import uvicorn

    host = os.getenv("RS_API_HOST", "127.0.0.1")
    port = int(os.getenv("RS_API_PORT", "8000"))
    uvicorn.run("research_system.api.app:create_app", factory=True, host=host, port=port)
