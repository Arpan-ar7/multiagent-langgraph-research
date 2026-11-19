"""Typed HTTP client for the research API (used by the Streamlit UI and tests).

Accepts any `httpx.Client`, so tests can pass FastAPI's `TestClient` directly.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

import httpx


def parse_sse(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Minimal Server-Sent Events parser: yields the JSON payload of each event."""
    data: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r")
        if not line:  # blank line terminates an event
            if data:
                yield json.loads("\n".join(data))
                data = []
            continue
        if line.startswith(":"):  # comment / keep-alive ping
            continue
        field, _, value = line.partition(":")
        if field == "data":
            data.append(value.removeprefix(" "))
    if data:
        yield json.loads("\n".join(data))


class ResearchClient:
    def __init__(
        self, base_url: str = "http://127.0.0.1:8000", http: httpx.Client | None = None
    ) -> None:
        self.http = http or httpx.Client(base_url=base_url, timeout=httpx.Timeout(30.0, read=None))
        self._cursor: dict[str, int] = {}  # thread_id -> number of events already yielded

    def _json(self, response: httpx.Response) -> Any:
        response.raise_for_status()
        return response.json()

    def health(self) -> dict[str, Any]:
        return self._json(self.http.get("/health"))  # type: ignore[no-any-return]

    def start(self, query: str, **options: Any) -> str:
        body = {"query": query, "options": {k: v for k, v in options.items() if v is not None}}
        return str(self._json(self.http.post("/runs", json=body))["thread_id"])

    def get(self, thread_id: str) -> dict[str, Any]:
        return self._json(self.http.get(f"/runs/{thread_id}"))  # type: ignore[no-any-return]

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._json(self.http.get("/runs", params={"limit": limit}))  # type: ignore[no-any-return]

    def review(self, thread_id: str, sub_questions: list[str] | None = None) -> dict[str, Any]:
        response = self.http.post(
            f"/runs/{thread_id}/review", json={"sub_questions": sub_questions}
        )
        return self._json(response)  # type: ignore[no-any-return]

    def resume(self, thread_id: str) -> dict[str, Any]:
        return self._json(self.http.post(f"/runs/{thread_id}/resume"))  # type: ignore[no-any-return]

    def events(self, thread_id: str, after: int | None = None) -> Iterator[dict[str, Any]]:
        """Follow a run's live events until its current execution ends.

        The server keeps every event of a run (first execution, then each resume) and numbers
        them 0, 1, 2, ... By default this continues after the last event this client already
        yielded for the run, so following a resumed run shows only the new events. Pass
        `after=0` to replay from the beginning.
        """
        start = self._cursor.get(thread_id, 0) if after is None else after
        headers = {"Last-Event-ID": str(start - 1)} if start > 0 else {}
        with self.http.stream("GET", f"/runs/{thread_id}/events", headers=headers) as response:
            response.raise_for_status()
            for event in parse_sse(response.iter_lines()):
                if event.get("type") == "end":
                    return
                start += 1
                self._cursor[thread_id] = start
                yield event
