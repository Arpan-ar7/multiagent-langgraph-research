# 15 · Status: what is done and what is left

Snapshot: **2026-11-19**. Git commits: Phase 0 `b440a1a` · 1 `36b5d4f` · 2 `c5899b0` · 3 `2847d94` · 4 `d269eeb` · 5 `c6d3862` (+ docs and CI fixes).

## ✅ Done

### Phase 0: Foundation
- [x] uv project, Python 3.13, dependencies, `.gitignore`, `.env.example`
- [x] ruff, mypy strict, pytest, pre-commit, nbstripout configured

### Phase 1: Experiments
- [x] Notebooks 01–06 run with real models; decisions logged
- [x] Notebook 07 built (stub error-injection parts verified)
- [x] Notebook 08 built and verified in dry-run mode

### Phase 2: Production code
- [x] Typed settings, LLM factory with role-based fallback chains
- [x] Pydantic schemas for every agent output
- [x] Four tools over Tavily, DuckDuckGo, arXiv, Wikipedia (never raise)
- [x] Five agents (planner, researcher, fact-checker, writer, critic)
- [x] LangGraph graph: parallel `Send`, critic loop, HITL `interrupt`, retry policies, error handlers
- [x] SQLite checkpoints with a safe serializer → crash resume
- [x] Code-built citations, grounding, credibility, Limitations section
- [x] `ResearchService` + CLI (`uv run research`)

### Phase 3: Testing and evaluation
- [x] 87 unit/integration tests with stub agents (no keys needed)
- [x] Evaluation harness: benchmark, deterministic metrics, LLM judge, resumable runner, LangSmith dataset + feedback
- [x] First real benchmark result (single_pass × technical: 5/4/5, grounding 1.00)

### Phase 4: API and UI
- [x] FastAPI: background runs, replayable SSE, review/resume endpoints, history
- [x] Streamlit UI: live timeline, plan approval, report with clickable citations, sources, rubric, timings, download, history, resume

### Phase 5: Polish
- [x] Dockerfile (multi-stage, non-root, healthcheck) + docker-compose (API + UI) + `.dockerignore`
- [x] GitHub Actions CI (lint, format, types, tests, Docker build + compose smoke test)
- [x] ADRs 0001–0005, README updated (Mermaid diagram, Docker, CI sections)
- [x] Fixes from real runs: retired Groq models, Groq JSON-schema structured output, quota errors no longer hidden, Groq retry budget, Groq moved to last fallback, LangSmith feedback ids
- [x] These project notes + `docs/START-HERE.md`
- [x] Pushed to GitHub (https://github.com/Arpan-ar7/multiagent-langgraph-research); **CI green**: lint, types, 87 tests, Docker build and compose smoke test

## ⏳ Left to do

| # | Task | Blocked by | How |
|---|---|---|---|
| 1 | Run the Docker image on this PC (it already works in CI) | WSL2 not installed | Admin PowerShell: `wsl --install`, restart, start Docker Desktop, `docker compose up --build` |
| 2 | Set the GitHub repo description and topics | Needs the web UI | Repo page → ⚙️ next to "About" → paste the description and topics |
| 3 | Finish the benchmark (9 of 10 pairs left) | OpenRouter free quota (~50 requests/day; one run ≈ 37) | `uv run research-eval --max-runs 1` once a day, or add $10 of credits (→ 1,000 free requests/day) and run all at once |
| 4 | Put the eval results table into README | #3 | `uv run research-eval --summary` |
| 5 | Re-run notebook 07 with healthy quota | Quota | Delete `data/07_checkpoints.sqlite`, then Restart & Run All |
| 6 | Run notebook 08 for real | Quota | Set `DRY_RUN = False` |
| 7 | Demo GIF for the README | A good real run | Record the Streamlit UI during a run (e.g. ScreenToGif), save as `docs/demo.gif` |
| 8 | (Optional) Deploy | #1 | Render / Hugging Face Spaces (Docker) or Streamlit Community Cloud |
| 9 | (Optional) Stretch goals | — | Local PDF/RAG agent (Chroma), Exa or Semantic Scholar tools, cost-aware model router, MCP server |

## Known limitations (honest list)

- The free tiers make full benchmark runs slow (quota).
- Groq's free tier (8k tokens/minute) cannot carry parallel researchers, so it is a rescue model only.
- The API's live event log is in memory: after an API restart, finished state is still there (checkpoints), but the fine-grained timeline is not.
- Credibility scoring is rule-based (transparent, not perfect).
