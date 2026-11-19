# 17 · Bugs found and lessons learned

Real problems we hit, how we found them, and how we fixed them. Great material for interviews ("tell me about a hard bug"). Full details: `docs/experiments-log.md`.

## Phase 1–3

| Bug | How found | Fix | Lesson |
|---|---|---|---|
| OpenRouter calls "hung" for minutes | nb 01 | Its `timeout` is in **ms**; the factory converts seconds → ms (+ test) | Read SDK units; test them |
| All research lost when the quota hit at the writer | nb 07 | SQLite checkpointer; runs resume at the failed node | Long LLM workflows must persist state |
| `error_handler` did nothing for researchers | nb 05 | Researchers catch their own errors (Send tasks bypass handlers) | Verify framework behaviour in a notebook |
| LangGraph retried errors it shouldn't, and skipped some it should | nb 07 | Explicit `retry_on=is_retryable`; never retry daily quotas | Defaults are not your policy |
| Error logs leaked headers, cookies, account id | live CLI run | `describe(e)` = type + first line; never `repr()` | Logs are a data leak surface |
| Plan edits silently created invalid models | regression test | `with_sub_questions()` re-validates; Pydantic warnings fail tests | `model_copy(update=)` skips validation |
| Dry-run results could be mistaken for real ones | Phase 3 review | Separate checkpoint DB + results file for dry runs | Isolate fake data physically |
| Stub critic never looped in one config | Phase 3 | Stubs made stateless | Shared mutable state biases comparisons |

## Phase 5 (2026-11-19), found by real runs

1. **Retired Groq models.** With a Groq key, Groq went first, but `llama-3.3-70b-versatile` / `llama-3.1-8b-instant` now return 404.
   **Fix:** defaults → `openai/gpt-oss-120b` / `openai/gpt-oss-20b`, checked by listing Groq's models and probing structured output + tool calls.
2. **Quota errors hidden behind the first error.** LangChain's `with_fallbacks` re-raises the *first* error when all models fail. The Groq 404 hid OpenRouter's "free-models-per-day", so the stop was misclassified.
   **Fix:** our own `with_fallbacks()` raises `AllModelsFailedError` with every failure whenever any is a quota or transient error; the classifiers inspect all of them (6 new tests).
3. **Groq tool-name bug.** `gpt-oss-120b` sometimes called the schema tool `researchPlan` instead of `ResearchPlan`, and Groq rejected it (400 `tool_use_failed`, 1 of 4 calls).
   **Fix:** Groq structured output uses `method="json_schema"` (4/4, and passed for every schema).
4. **Groq's free tier is too small for parallel researchers.** 8,000 tokens/minute vs ~5k tokens per researcher call; notebook 07 had 0/6, then 1/6 researchers succeed.
   **Fix:** Groq retry budget 4 (waits out `retry-after`), and **Groq moved to the last fallback** by default (`RS_GROQ_POSITION`).
5. **LangSmith SDK deprecation:** feedback now passes `session_id` and `trace_id`.

## Big lessons

- **Real runs find bugs that unit tests can't.** Every Phase 5 bug came from the first real benchmark run.
- **Measure before deciding** (notebooks): every design choice has evidence.
- **Free tiers shape architecture:** quotas → checkpoints and resumable evals; rate limits → fallbacks and retry classification.
- **Let code do what rules can decide:** citations, approval and limits in code are cheaper, testable and reliable.
