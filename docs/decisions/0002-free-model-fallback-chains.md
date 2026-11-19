# ADR 0002: Role-based fallback chains of free models

**Status:** Accepted

## Context
The project must run on free tiers. In notebook 01, free OpenRouter models were rate-limited or unavailable unpredictably (one returned 429 on every call), and the daily quota (about 50 requests) is smaller than a few research runs. A Groq key may or may not be available.

## Decision
- Models are chosen per **role** (`reasoning`, `worker`, `judge`). Each role has an ordered fallback chain configured in `Settings` and overridable with `RS_*_MODELS`.
- Structured output is bound to each model *before* chaining the fallbacks (nb 02), with a bounded repair loop for validation errors.
- When `GROQ_API_KEY` is set, Groq joins each chain. By default it goes **last**, as a rescue model, because its free tier allows only 8,000 tokens/minute, too little for parallel researchers (Phase 5 finding). `RS_GROQ_POSITION=first` makes it primary on a paid tier. The judge chain is never changed, so evaluation stays independent of the system's own models.
- Retries use `retry_on=is_retryable`: 429/5xx/network errors are retried, exhausted daily quotas are not. The run stops instead and can be resumed from its checkpoint.

## Consequences
- A single model outage degrades the run's speed, not its success.
- Results depend on which model in the chain answered. The LangSmith trace shows which model served each call.
- Quota stops are explicit and resumable instead of burning retries.
