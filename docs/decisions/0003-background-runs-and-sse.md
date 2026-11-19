# ADR 0003: Background runs with replayable SSE progress

**Status:** Accepted

## Context
A research run takes minutes and may pause for human plan approval. Tying the run to an HTTP request (or a Streamlit script rerun) would kill it when a browser tab closes or the UI reruns.

## Decision
- `POST /runs` returns `202` with a `thread_id`. A `RunManager` executes the graph in a worker thread that is independent of any connection.
- Progress is an append-only event log per run, streamed as Server-Sent Events. Each event has an id, so clients reconnect with `Last-Event-ID` and replay what they missed.
- State of record is the LangGraph SQLite checkpointer. History, reports, plan review (`/review`) and resume (`/resume`) all read from it, so they survive API restarts.
- Streamlit is a thin client over a typed HTTP client. Its timeline is a pure view model (`research_system.ui.timeline`) that is unit-tested without Streamlit.

## Consequences
- Closing the browser never stops a run; reopening it replays the timeline.
- The live event log is in memory, so after an API restart only checkpointed state (not the fine-grained timeline) is available.
- SSE is one-way, which is enough here. Commands go through ordinary POST endpoints.
