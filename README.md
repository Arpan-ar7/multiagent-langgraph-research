# Multi-Agent AI Research System

A research assistant built with **LangChain** and **LangGraph**. A team of LLM agents plans the research, searches the web and academic sources **in parallel**, fact-checks claims across sources, writes a report with **verifiable citations**, and critiques it, looping back for more research when it finds gaps.

> **Status:** Phase 2 (production code) is done: 48 tests pass and mypy strict is clean. Notebooks 07–08 still need their real LLM runs (API quota). See [docs/architecture.md](docs/architecture.md) and [docs/experiments-log.md](docs/experiments-log.md).

## How it works

```
Query → Planner → [Human review] → Researchers ×N (parallel) → Fact-checker → Writer → Critic
                                        ▲                                              │
                                        └──────── follow-up questions (bounded loop) ◄─┘
                                                                     approved → Final report
```

| Agent | What it does |
|---|---|
| Planner | Breaks the question into 3–5 focused, searchable sub-questions and a report outline |
| Researcher (×N) | ReAct tool-calling agent (Tavily, DuckDuckGo, arXiv, Wikipedia); returns claims tied to source URLs |
| Fact-checker | Drops claims citing URLs that were never retrieved, scores source credibility, flags contradictions |
| Writer | Writes Markdown with `[n]` markers; code builds the References, so they are correct by construction |
| Critic | Rubric scores (1–5); code decides approval; gaps become new parallel research tasks |

Engineering highlights:
- **Resilience:** per-role model fallback chains, explicit retry policy (no retries on exhausted quotas), graceful degradation, and **SQLite checkpoints, so any crashed run resumes** where it stopped.
- **Human-in-the-loop:** optional plan approval via LangGraph `interrupt`.
- **Testable by design:** the graph depends only on agent interfaces, so integration tests run the real graph with stub agents in about 8 s, with no API calls.

## Tech stack

LangGraph · LangChain (`create_agent`, middleware, structured output) · OpenRouter (free models) · Groq (optional, used first when configured) · Tavily · arXiv · Wikipedia · LangSmith · Pydantic · structlog · pytest · mypy (strict) · ruff · uv

## Setup

```bash
uv sync                      # create .venv and install everything
cp .env.example .env         # then paste your API keys
uv run pre-commit install    # lint and clean notebook metadata on commit
```

Keys: `OPENROUTER_API_KEY` and `TAVILY_API_KEY` (required), `LANGSMITH_API_KEY` (tracing, recommended), `GROQ_API_KEY` (optional). All have free tiers. The OpenRouter free tier allows about 50 requests/day, and one research run uses roughly 15–35.

## Usage

```bash
uv run research "How are AI coding agents changing software engineering in 2026?"
uv run research "..." --sub-questions 3 --iterations 1     # cheaper run
uv run research "..." --review                             # approve/edit the plan first
uv run research --resume <thread-id>                       # continue a paused or interrupted run
```

Reports are saved to `reports/`. Defaults can be overridden with `RS_*` environment variables (see `src/research_system/config/settings.py`).

## Development

```bash
uv run pytest                 # unit + integration (no network)
uv run pytest -m live         # smoke tests against real APIs (uses quota)
uv run ruff check . && uv run mypy src
```

## Project layout

```
notebooks/            Phase 1 experiments (01–08), each ending with observations & decisions
src/research_system/  config · schemas · prompts · tools · agents · graph · utils · service · cli
tests/                unit · integration · live
docs/                 architecture, decision records, experiment log
reports/              generated reports (gitignored)
```

## Roadmap

- [x] Phase 0: Foundation and tooling
- [~] Phase 1: Jupyter experiments (01–06 done; 07–08 real runs pending quota)
- [x] Phase 2: Production implementation
- [ ] Phase 3: Evaluation (LangSmith datasets, LLM-as-judge) and test hardening
- [ ] Phase 4: FastAPI + Streamlit UI
- [ ] Phase 5: Docker, CI, docs, demo
