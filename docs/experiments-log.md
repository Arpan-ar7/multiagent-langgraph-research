# Experiments Log

Decisions from the Phase 1 notebooks, with the evidence behind each. Production code (Phase 2) implements these decisions.
Runs: 2026-11-18/19, OpenRouter free tier (no Groq key yet).

## 01 · LLM providers (`notebooks/01_llm_providers.ipynb`, data: `data/01_model_benchmark.csv`)

| Model | Latency | Tool call | Structured output |
|---|---|---|---|
| nvidia/nemotron-3.5-super-vl:free | 4.7 s | ✅ | ✅ |
| baidu/ernie-5.5-flash-preview:free | **1.8 s** | ✅ | ✅ |
| inclusionai/ling-3.2-flash:free | 38.2 s | ✅ | ✅ |
| google/gemma-4-31b-it:free | n/a (HTTP 429 upstream) | n/a | n/a |

- **Decision:** reasoning roles (planner, fact-checker, critic) use Nemotron; worker roles (researcher, writer) use Ernie; each falls back to the other, then Ling.
- **Decision:** a provider-agnostic `make_model()` factory; Groq models are put first in each chain automatically once `GROQ_API_KEY` is set.
- **Gotcha:** `ChatOpenRouter(timeout=...)` is in **milliseconds**. `timeout=20` made calls "hang" for minutes while the SDK retried. The factory always takes seconds.

## 02 · Prompting & structured output

- **Decision:** Pydantic structured output for every decision-making agent; `Field` descriptions are prompt text.
- **Decision:** build structured runnables **per model, then add fallbacks**. Proxying `with_structured_output` through a fallback wrapper breaks on fake test models.
- **Finding:** Pydantic validation errors arrive in waves (item errors before list-length errors), so repair is a bounded loop (≤2 attempts).
- **Finding:** a one-shot example did *not* make sub-questions more concrete (5/5 → 4/4 concrete). The planner stays **zero-shot**, to be revisited in evals.

## 03 · Tools & search (data: `data/03_search_comparison.csv`)

- Tavily: ~2–5 s, ~1,200 chars per result, relevance-scored. Extract returns 20–30k-char pages, so they are truncated to 4,000.
- DuckDuckGo (`ddgs`): **intermittent** (one probe failed on every backend, another run worked), snippets 3–5× shorter. Best-effort fallback only.
- arXiv: relevance sort mixes in old papers; **date sort destroys relevance**. Use relevance sort with years in the query.
- **Decision:** unified `SearchResult` schema; tools never raise (they return `ERROR: ... try X`); results are numbered with URLs for citation.

## 04 · Researcher (ReAct agent)

- **Decision:** `create_agent` + `ToolStrategy(Finding)` + middleware (model fallback, ≤4 tool calls, ≤7 model calls).
- Finding: models request tools in parallel. The limit middleware blocks the excess (6 requested → 2 blocked).
- Finding: a typical sub-question takes 4 model calls, ~11–14 s and ~15k tokens. All 4 cited URLs were grounded.

## 05 · LangGraph fundamentals

- `Send` fan-out: 5 × 1 s tasks finished in 1.01 s.
- **Finding (LangGraph 1.2.17):** node `error_handler` must return a `Command` with `goto`, and **does not apply to `Send` tasks**.
- **Decision:** researchers catch their own errors and return a failure record; sequential nodes use `RetryPolicy` + `error_handler`.

## 06 · Individual agents (synthetic fixtures with planted problems)

- The fact-checker caught **both** planted problems: the 58% vs <30% contradiction (LLM) and the fabricated citation (deterministic grounding).
- The writer produced 0 citation problems. References are built by code, so they are correct by construction.
- Critic: rubric scores; **code** decides approval (all scores ≥ 4).
- One fact-check → write → critique pass costs 3 LLM calls (~42 s).

## 07 · Orchestration

- The full graph ran through planning → human approval → 3 parallel researchers → fact-check, then hit the **free-models-per-day** quota at the writer. With in-memory checkpoints, all research was lost.
- **Decision:** `SqliteSaver` + an allowlist serializer. A crashed run resumes at the failed node (verified: researchers are not re-run).
- **Decision:** explicit `retry_on`. LangGraph's default skips `RuntimeError`/`ValueError`/`OSError` and retries unknown types.
- Stub-agent error injection (dependency injection) runs in 0.2 s and covers a failed researcher, a skipped fact-check and a critic loop.
- ⏳ The real end-to-end run is pending quota.

## 08 · Evaluation

- The pipeline is verified in `DRY_RUN` mode: the callback counter sees calls inside parallel threads (7 calls single pass, 11 with the loop).
- ⏳ Real `single_pass` vs `critic_loop` results are pending quota (~180 requests for 3 questions × 2 configs).

## Phase 2 · Findings while productionising

- **Bug found by tests:** trimming a plan to fewer than 3 sub-questions (`--sub-questions 2`, or plan review) created an *invalid* `ResearchPlan`, because `model_copy(update=)` skips validation. When LangGraph restores a checkpoint, it tries `cls(**data)` and, on validation failure, **silently falls back to `model_construct`**, which leaves nested models as dicts. A resumed run could then crash on `q.question`.
  **Fix:** the schema invariant is now 1–5 (the LLM is still asked for 3–5), plan edits go through the validating `ResearchPlan.with_sub_questions()`, and pytest turns `UserWarning` (Pydantic serializer warnings) into errors.
- Run options moved from `config` into the graph state, so a resumed run keeps the options it started with.
- **Live CLI check against an exhausted quota:** each fallback model was tried once, the daily-quota error was *not* retried, and the run stopped cleanly with a resume command. Logging `repr()` of provider errors leaked response headers, cookies and the account id into logs, so errors are now logged with `describe()` (type + first line).

## Phase 3 · Evaluation harness

- Built `research_system/evals`: benchmark set (5 question types), deterministic metrics, LLM judge on a dedicated `judge` model chain (Ling → Nemotron, not the writer's model), resumable runner, LangSmith dataset sync and per-run feedback.
- **Dry-run bug 1:** dry-run threads shared the real checkpoint DB and thread ids, so a real eval would have found "finished" fake runs and scored them as results. Dry runs now use `checkpoints-dryrun.sqlite`.
- **Dry-run bug 2:** the stub critic kept call counts per question across configurations, so `critic_loop` never looped. Stubs are now stateless (they decide from the report content). The lesson: shared mutable state between evaluated runs silently biases comparisons.
- mypy caught stub parameter names that didn't match the agent `Protocol`s (keyword callers would break).
- Verified: re-runs skip finished pairs, `--max-runs` caps a session, and the LangSmith dataset sync is idempotent (5 examples).
- ⏳ Real results: about 17 requests per single-pass run and up to about 32 with the critic loop (including the judge), so 3 questions × 2 configs needs about 3 days on the free tier (50/day) or one session with credits.
