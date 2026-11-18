# Multi-Agent AI Research System

A research assistant built with **LangChain** and **LangGraph**. A team of LLM agents plans the research, searches the web and academic sources in parallel, checks claims across sources, writes a report with citations, and reviews it, repeating until the report is good enough.

> **Status:** Phase 0 (foundation) is done. Next up: Phase 1 (notebook experiments).

## Architecture (planned)

```
Query → Planner → [Human review] → Researchers ×N (parallel) → Fact-checker → Writer → Critic
                                        ▲                                              │
                                        └──────── follow-up questions (bounded loop) ◄─┘
                                                                     approved → Final report
```

| Agent | Role |
|---|---|
| Planner | Breaks the question into focused sub-questions and a report outline |
| Researcher (×N) | Tool-calling agent: Tavily, DuckDuckGo, arXiv, Wikipedia |
| Fact-checker | Removes duplicate sources, scores credibility, flags conflicting claims |
| Writer | Writes a Markdown report with inline citations |
| Critic | Scores the report and sends follow-up questions when it finds gaps |

## Tech stack

LangGraph · LangChain · Groq (primary LLM) · OpenRouter (fallback) · Tavily · LangSmith · Pydantic · FastAPI · Streamlit · uv

## Setup

```bash
uv sync                      # create .venv and install everything
cp .env.example .env         # then paste your API keys
uv run pre-commit install    # lint and strip notebook outputs on commit
uv run pytest                # run tests
uv run research --help       # CLI
```

Required keys: `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `TAVILY_API_KEY`, `LANGSMITH_API_KEY` (all have free tiers).

## Project layout

```
notebooks/            Phase 1 experiments
src/research_system/  config · prompts · schemas · tools · agents · graph · utils · api · cli
ui/                   Streamlit front end
tests/                unit · integration · evals
docs/                 architecture notes, decision records, experiment log
reports/              generated reports (gitignored)
```

## Roadmap

- [x] Phase 0: Foundation and tooling
- [ ] Phase 1: Jupyter experiments
- [ ] Phase 2: Production implementation
- [ ] Phase 3: Tests and evaluation
- [ ] Phase 4: FastAPI + Streamlit UI
- [ ] Phase 5: Docker, CI, docs, demo
