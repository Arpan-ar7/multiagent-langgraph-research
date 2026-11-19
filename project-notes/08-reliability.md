# 08 · Reliability: errors, retries, resume

Files: `graph/builder.py`, `utils/errors.py`, `graph/checkpointing.py`, `service.py`. Status: ✅ (tests: `tests/integration/test_graph.py` covers failures, the critic loop and crash-resume).

The goal: **a single failure should degrade the report, not kill the run; and any stopped run can be continued.**

## What happens when…

| Failure | What the system does | Where |
|---|---|---|
| One model is rate-limited or down | The next model in the role's chain answers | `config/llm.py` |
| Transient error (429 per-minute, 5xx, timeout) in a sequential node | `RetryPolicy`: 3 attempts, 2 s → 4 s backoff | `graph/builder.py` |
| Daily quota exhausted | **No retry** (pointless); the run stops cleanly and can be resumed | `utils/errors.py` |
| One researcher fails | Recorded in `failures`; others continue; the report lists it under "Limitations" | `researcher` node |
| Fact-checker fails | Claims pass through unchecked with a warning | `fact_check_failed` handler |
| Critic fails | Report is finalized without review, with a warning | `critic_failed` handler |
| Invalid structured output | Up to 2 repair attempts with the error fed back | `invoke_structured` |
| Agent loops forever | Tool-call limit, model-call limit, `max_iterations`, `recursion_limit` | middleware + options |
| Search provider down | Tavily → DuckDuckGo; tools return `ERROR: ... try X` instead of raising | `tools/` |
| Process crash / laptop closed | Resume from the last checkpoint | SQLite checkpointer |

## Error classification (`utils/errors.py`)

- `is_quota_exhausted(e)`: the error text contains "per-day", "daily", "quota" or "insufficient credits". For an `AllModelsFailedError`, true if any inner error is a quota error.
- `is_retryable(e)`: never for quota errors; yes for connection errors/timeouts, HTTP 429 and 5xx.
- `describe(e)`: a short, safe one-line description. We never log `repr()` of provider errors, because it leaked response headers, cookies and account ids (found in Phase 2).

## Resume

Every step is checkpointed in `data/checkpoints.sqlite` under the run's `thread_id`. The service's `snapshot()` reads a run's status:

| Status | Meaning | What `stream()` does next |
|---|---|---|
| `new` | nothing yet | start with the query |
| `awaiting_review` | paused at `interrupt` | resume with the human's decision |
| `incomplete` | crashed or stopped mid-run | continue at the failed node (finished nodes are **not** re-run) |
| `done` | report exists | nothing |

CLI: `uv run research --resume <thread-id>`. API: `POST /runs/{id}/resume`. UI: a "Resume" button.

Run options are stored **inside the state** (not only in the config), so a resumed run keeps the options it started with.
