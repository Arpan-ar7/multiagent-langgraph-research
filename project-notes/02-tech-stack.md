# 02 · Tech stack

## Services (API keys in `.env`)

| Service | Used for | Needed? | Notes |
|---|---|---|---|
| **OpenRouter** | Main LLM provider (free models) | Required | One key → many models. Free tier ≈ 50 requests/day, resets 00:00 UTC. |
| **Groq** | Rescue LLM (very fast) | Optional | Free tier: 1,000 requests/day but only **8,000 tokens/minute** per model, so it is the *last* fallback by default. |
| **Tavily** | Main web search + page extraction | Required | Built for LLM agents: clean snippets with relevance scores. ~1,000 credits/month free. |
| **LangSmith** | Tracing, datasets, evaluation feedback | Recommended | Shows every agent step, model, tokens and timing. |
| arXiv, Wikipedia, DuckDuckGo | Papers, background, backup web search | No key | Free. DuckDuckGo is unreliable, so it is only a fallback. |

Models in use (see `src/research_system/config/settings.py`):
- **reasoning** role (planner, fact-checker, critic): Nemotron 3.5 → Ernie 5.5 → Ling 3.2 (+ Groq `openai/gpt-oss-120b` last)
- **worker** role (researcher, writer): Ernie 5.5 → Nemotron 3.5 → Ling 3.2 (+ Groq `openai/gpt-oss-20b` last)
- **judge** role (evaluation only): Ling 3.2 → Nemotron 3.5 (deliberately different from the writer, to reduce self-preference bias)

## Libraries

| Area | Library | What it does for us | Where |
|---|---|---|---|
| Orchestration | **LangGraph** | The state machine: nodes, edges, parallel `Send`, loops, checkpoints, interrupts, streaming | `graph/` |
| Agents | **LangChain** (`create_agent`, middleware) | The researcher's ReAct loop, tool calling, structured output, model fallbacks | `agents/` |
| LLM clients | `langchain-openrouter`, `langchain-groq` | Talk to the providers | `config/llm.py` |
| Search | `langchain-tavily`, `ddgs`, `arxiv`, `wikipedia` | Search adapters | `tools/providers.py` |
| Persistence | `langgraph-checkpoint-sqlite` | Saves state after each step → resume, history, human-in-the-loop | `graph/checkpointing.py` |
| Data models | **Pydantic** v2, `pydantic-settings` | Typed schemas for every LLM output; typed config from env vars | `schemas/`, `config/settings.py` |
| Retries | `tenacity`, LangGraph `RetryPolicy` | Retry transient failures | `graph/builder.py` |
| Logging | `structlog` | Structured, readable logs | `utils/logging.py` |
| API | **FastAPI**, `sse-starlette`, `uvicorn` | HTTP API with live Server-Sent Events | `api/` |
| UI | **Streamlit** | Web front end | `ui/streamlit_app.py` |
| HTTP client | `httpx` | The UI's typed API client | `api/client.py` |
| Observability | `langsmith` | Traces, dataset, feedback scores | `evals/` |

## Developer tooling

| Tool | Why |
|---|---|
| **uv** | Fast package manager; `uv.lock` pins exact versions; `uv run` uses the project venv |
| **ruff** | Linter + formatter (replaces flake8, isort, black) |
| **mypy (strict)** | Static type checking: catches wrong arguments before running |
| **pytest** (+ pytest-asyncio) | Tests |
| **pre-commit** + **nbstripout** | Runs checks on commit; strips notebook metadata |
| Jupyter | Phase 1 experiments |
| **Docker**, docker compose | Packaging and running API + UI together |
| **GitHub Actions** | CI: lint, types, tests, Docker build + smoke test on every push |

Python version: **3.13** (`.python-version`).
