# 14 · Notebook journey (Phase 1)

We experimented in Jupyter **before** writing production code. Each notebook ends with "Observations & Decisions", and every decision is copied into `docs/experiments-log.md`. Helpers shared by the notebooks: `notebooks/nb_setup.py` (keys, LLM cache), `nb_components.py` (models, schemas, tools), `nb_agents.py` (agents).

| # | Notebook | What we learned / decided | Status |
|---|---|---|---|
| 01 | `01_llm_providers` | Benchmarked free models: Ernie fastest (1.8 s), Nemotron solid (4.7 s), Ling slow (38 s), Gemma always 429. Picked models per role with fallbacks. Gotcha: OpenRouter timeout is in ms. | ✅ |
| 02 | `02_prompting_structured_output` | Pydantic structured output for all agents; build structured runnables per model, *then* add fallbacks; validation errors arrive in waves, so repair is a bounded loop; a few-shot example did not help, so the planner stays zero-shot. | ✅ |
| 03 | `03_tools_search` | Tavily best; DuckDuckGo intermittent; arXiv needs relevance sort + years; tools never raise and return numbered results with URLs. | ✅ |
| 04 | `04_single_agent_react` | ReAct researcher with `create_agent` + `ToolStrategy(Finding)` + limit middleware; ~4 model calls, ~12 s, ~15k tokens per sub-question; all cited URLs grounded. | ✅ |
| 05 | `05_langgraph_fundamentals` | StateGraph, reducers, `Send` (5 × 1 s tasks in 1.01 s), subgraphs, checkpoints, `interrupt`, streaming. **Gotcha:** `error_handler` doesn't cover `Send` tasks. | ✅ |
| 06 | `06_individual_agents` | Planner, fact-checker, writer, critic tested on fixtures with planted problems: the fact-checker caught both the planted contradiction and the fake citation. | ✅ |
| 07 | `07_multi_agent_orchestration` | Full graph, HITL, crash → resume (in-memory checkpoints lost research, hence SQLite), error injection with stubs. | 🟡 Ran end to end on 2026-11-19, but with OpenRouter's quota exhausted only 1 of 6 researchers succeeded on Groq (8k tokens/minute). Re-run after the quota resets. |
| 08 | `08_evaluation` | Judge rubric, config comparison, charts; pipeline verified in `DRY_RUN` mode. | ⏳ Real run pending (set `DRY_RUN = False` when quota allows) |

## Why notebooks first?

- Cheap experiments with real models before committing to a design.
- Every production decision has **evidence** (numbers, failures seen) behind it. That is good for interviews ("we chose X because we measured Y").
- An LLM response cache (`data/llm_cache.sqlite`) makes re-running notebooks free.
