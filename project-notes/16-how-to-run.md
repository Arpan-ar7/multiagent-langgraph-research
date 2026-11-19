# 16 · How to run everything

## First-time setup

```bash
uv sync                      # create .venv and install everything from uv.lock
cp .env.example .env         # then paste your keys: OPENROUTER_API_KEY, TAVILY_API_KEY (required),
                             # LANGSMITH_API_KEY (recommended), GROQ_API_KEY (optional)
uv run pre-commit install    # checks on every commit
```

## Research from the terminal

```bash
uv run research "How are AI coding agents changing software engineering in 2026?"
uv run research "..." --sub-questions 3 --iterations 1     # cheaper run
uv run research "..." --review                             # approve/edit the plan first
uv run research --resume <thread-id>                       # continue a stopped run
```

Reports are saved in `reports/`. Traces appear in LangSmith if tracing is on.

## Web UI (two terminals)

```bash
uv run research-api                          # API → http://127.0.0.1:8000 (docs at /docs)
uv run streamlit run ui/streamlit_app.py     # UI  → http://localhost:8501
```

## Docker (after installing WSL2 + Docker Desktop)

```bash
docker compose up --build    # API :8000 + UI http://localhost:8501
docker compose down          # stop (add -v to also delete the data volume)
```

## Evaluation

```bash
uv run research-eval --dry-run          # free pipeline check with stubs
uv run research-eval --max-runs 1       # real runs, resumable across days
uv run research-eval --summary          # results table
```

## Quality checks (same as CI)

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src ui && uv run pytest
uv run pytest -m live                   # real-API smoke tests (uses quota)
```

## Useful settings (env vars, or in `.env`)

| Variable | Default | Meaning |
|---|---|---|
| `RS_MAX_SUB_QUESTIONS` | 4 | sub-questions per plan (1–5) |
| `RS_MAX_TOOL_CALLS` | 4 | tool calls per researcher |
| `RS_MAX_ITERATIONS` | 2 | critic rounds |
| `RS_APPROVAL_THRESHOLD` | 4 | minimum critic score to approve |
| `RS_HUMAN_REVIEW` | false | pause for plan approval |
| `RS_GROQ_POSITION` | last | `first` makes Groq the primary model |
| `RS_GROQ_MAX_RETRIES` | 4 | Groq retries for per-minute limits |
| `RS_REASONING_MODELS` / `RS_WORKER_MODELS` | see settings | e.g. `"openrouter:a/b:free, groq:c"` |
| `RS_API_HOST` / `RS_API_PORT` | 127.0.0.1 / 8000 | API bind address |
| `RESEARCH_API_URL` | http://127.0.0.1:8000 | where the UI finds the API |

## Quotas

- OpenRouter free: ~50 requests/day, reset at **00:00 UTC**. One full run ≈ 15–37 requests.
- Check a stopped run: it prints `Resume later with: uv run research --resume <id>`.
