# 03 · Project structure (every file, its job, its status)

Rule we follow: **one clear job per file**. Prompts live apart from agent logic, schemas apart from behaviour, and tools never import agents.

```
MultiAgentResearchSystem/
├── src/research_system/      ← the production package (Phase 2+)
├── ui/streamlit_app.py       ← web UI (Phase 4)
├── tests/                    ← unit, integration, live tests (Phase 3+)
├── notebooks/                ← Phase 1 experiments 01–08
├── docs/                     ← architecture, decision records (ADRs), experiment log
├── project-notes/            ← these notes
├── data/                     ← checkpoints, LLM cache, benchmark CSVs (mostly gitignored)
├── reports/                  ← generated reports (gitignored)
├── Dockerfile, docker-compose.yml, .dockerignore   ← Phase 5
├── .github/workflows/ci.yml  ← Phase 5
├── pyproject.toml, uv.lock   ← dependencies, tool config, console scripts
└── .env / .env.example       ← API keys (the real .env is never committed)
```

## `src/research_system/` file by file

| File | Job | Status |
|---|---|---|
| `config/settings.py` | All configuration as a typed `Settings` class. Reads `.env` and `RS_*` env vars. Model chains per role, limits, paths, `groq_position`. | ✅ |
| `config/llm.py` | **LLM factory**: builds models per role with fallbacks, structured output (JSON-schema mode on Groq), repair loop, `with_fallbacks()` that reports every failure | ✅ |
| `schemas/plan.py` | `ResearchPlan`, `SubQuestion` (planner output) | ✅ |
| `schemas/findings.py` | `Finding`, `Claim` (researcher output) | ✅ |
| `schemas/review.py` | `ConflictReport`, `VerifiedClaim`, `FactCheckReport`, `Critique` | ✅ |
| `schemas/report.py` | `Draft` (writer output: Markdown + URL→number map) | ✅ |
| `schemas/search.py` | `SearchResult`: one shape for every search provider | ✅ |
| `prompts/templates.py` | All prompt texts (planner, researcher, fact-checker, writer, critic) | ✅ |
| `tools/providers.py` | Adapters: Tavily, DuckDuckGo, arXiv, Wikipedia → `SearchResult`; `search_with_fallback` | ✅ |
| `tools/research_tools.py` | The 4 LangChain tools the researcher uses: `web_search`, `search_papers`, `search_wikipedia`, `fetch_page` | ✅ |
| `agents/base.py` | Agent interfaces (`Protocol`s) and the `Agents` container injected into the graph | ✅ |
| `agents/planner.py` … `critic.py` | The five agents (note 05) | ✅ |
| `agents/__init__.py` | `build_agents(settings)`: wires real agents to models and tools | ✅ |
| `graph/state.py` | `ResearchState` (shared state) and `ResearcherTask` (private payload for each parallel researcher) | ✅ |
| `graph/builder.py` | **The LangGraph graph**: nodes, edges, routing, retries, error handlers | ✅ |
| `graph/options.py` | `RunOptions` (per-run knobs) stored in state so resumed runs keep them | ✅ |
| `graph/checkpointing.py` | SQLite checkpointer with a safe serializer (only our schema types) | ✅ |
| `utils/citations.py` | Number sources, validate `[n]` markers, build References, source table | ✅ |
| `utils/sources.py` | Rule-based domain credibility (0.9 / 0.7 / 0.5) | ✅ |
| `utils/errors.py` | `describe()` (safe error text), `is_quota_exhausted`, `is_retryable`, `AllModelsFailedError` | ✅ |
| `utils/logging.py` | structlog setup | ✅ |
| `service.py` | **`ResearchService`**: the single entry point. Start, stream, review, resume, list, snapshot, save. | ✅ |
| `cli.py` | `uv run research ...` | ✅ |
| `api/app.py` | FastAPI app and endpoints; `research-api` entry point (host/port via `RS_API_HOST`/`RS_API_PORT`) | ✅ |
| `api/runs.py` | `RunManager`: runs graphs in background threads with a replayable event log | ✅ |
| `api/schemas.py` | API request/response models | ✅ |
| `api/client.py` | Typed HTTP client + SSE parser (used by the UI) | ✅ |
| `ui/timeline.py` | Pure view model: turns events into the UI's agent timeline (unit-tested) | ✅ |
| `evals/dataset.py` | 5 benchmark questions + LangSmith dataset sync | ✅ |
| `evals/metrics.py` | Deterministic metrics, token/call counter, `Judge` (LLM-as-judge) | ✅ |
| `evals/runner.py` | Resumable evaluation runner + LangSmith feedback | ✅ |
| `evals/stubs.py` | Stub agents for free dry runs | ✅ |
| `evals/report.py`, `evals/cli.py` | Results table; `uv run research-eval` | ✅ |

## Other folders

| Path | Contents | Status |
|---|---|---|
| `ui/streamlit_app.py` | Streamlit UI (only talks HTTP to the API) | ✅ |
| `tests/unit/` | Schemas, settings, tools, citations, retry logic, LLM factory, fallbacks, evals, timeline | ✅ |
| `tests/integration/` | The real graph with stub agents, the API, the UI view model | ✅ |
| `tests/live/` | Real API smoke tests (`-m live`, skipped by default) | ✅ |
| `tests/conftest.py` | Deterministic stub agents shared by tests | ✅ |
| `notebooks/01–08` + `nb_*.py` helpers | Experiments (note 14) | 🟡 07 ran in a degraded state, 08 dry-run only |
| `docs/architecture.md` | Architecture, design decisions, error-handling table | ✅ |
| `docs/decisions/0001–0005` | Architecture Decision Records | ✅ |
| `docs/experiments-log.md` | Every experiment finding and decision, with evidence | ✅ |
