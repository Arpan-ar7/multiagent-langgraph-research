# 10 · Service, CLI, API and UI

Status: ✅ all built and tested (`tests/integration/test_api.py`, `test_ui.py`, `tests/unit/test_timeline.py`); 🟡 the Docker version is not yet run (note 13).

## Layers

```
 CLI (cli.py)        Streamlit UI (ui/streamlit_app.py)
      │                       │ HTTP + SSE (api/client.py)
      │               FastAPI (api/app.py) ── RunManager (api/runs.py, background threads)
      │                       │
      └────────► ResearchService (service.py) ◄── one entry point for everyone
                              │
                  LangGraph graph + SQLite checkpointer
```

## ResearchService (`service.py`)

The one class everything uses. It builds the graph with real agents and the SQLite checkpointer, then offers:
- `stream(thread_id, query=..., options=..., decision=...)`: advances a run from wherever it is (new / paused / incomplete) and yields simple JSON events: `progress`, `review`, `resumed`, `error`, `done`
- `snapshot(thread_id)`: status, plan, report, critique, failures, warnings, metrics, source table
- `list_runs()`: history from the checkpointer
- `run()` (blocking) and `save_report()` (writes `reports/<date>-<slug>.md`)

## CLI (`cli.py`): `uv run research`

```bash
uv run research "question"                          # full run
uv run research "question" --sub-questions 3 --iterations 1   # cheaper
uv run research "question" --review                 # approve or edit the plan first
uv run research --resume <thread-id>                # continue a stopped run
```

Progress prints live: `[researcher] started: ...`, `[critic] reviewing`, then the critic scores and the report path.

## API (`api/app.py`, `api/runs.py`): `uv run research-api`

| Endpoint | Purpose |
|---|---|
| `POST /runs` | Start a run → `202 Accepted` + `thread_id` |
| `GET /runs/{id}/events` | Live progress as **Server-Sent Events** (replayable with `Last-Event-ID`) |
| `POST /runs/{id}/review` | Approve or narrow the plan of a paused run |
| `POST /runs/{id}/resume` | Continue an interrupted run |
| `GET /runs/{id}` · `/runs/{id}/report` · `/runs` · `/health` | State, Markdown report, history, status |

Key design (ADR 0003): a run executes in a **background thread**, not inside the HTTP request. Events go into an in-memory, append-only log per run. Clients read the log from any position, so closing the browser never stops a run, and reconnecting replays what was missed. The state of record is the checkpointer, so history and reports survive API restarts. Interactive docs: http://127.0.0.1:8000/docs.

**SSE (Server-Sent Events)** is a simple one-way stream over HTTP: the server keeps the response open and writes `id: 5\ndata: {...}\n\n` blocks. It is lighter than WebSockets and enough here, because commands go through normal POST endpoints.

## Streamlit UI (`ui/streamlit_app.py`)

Run it with `uv run streamlit run ui/streamlit_app.py` → http://localhost:8501 (`RESEARCH_API_URL` points it at another API). It offers:
- a query box and settings (sub-questions, tool calls, iterations, human review)
- a **live agent timeline**: which agent is running, each researcher's state, critic follow-up rounds
- a plan-approval editor when paused
- the report with clickable `[n]` citations, a source table with credibility, the critic rubric, per-agent timings, a Markdown download
- run history, and resume of interrupted runs with one click

The UI only talks HTTP. Its timeline logic lives in `src/research_system/ui/timeline.py` as a pure, unit-tested **view model** (events in → stage states out), so it is testable without Streamlit.
