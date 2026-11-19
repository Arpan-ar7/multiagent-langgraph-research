# 07 · Models, fallbacks and structured output

Files: `src/research_system/config/llm.py` (factory) and `config/settings.py` (model lists). Status: ✅ (tests: `tests/unit/test_llm.py`, `tests/unit/test_fallbacks.py`)

## Why we need fallbacks

Free models fail often: rate limits (429), daily quotas, providers being down, models being retired. In notebook 01 one free model returned 429 on *every* call. So **no agent depends on a single model**.

## Roles, not models

Agents ask for a **role**, never a model name:

| Role | Used by | Chain (first → last) |
|---|---|---|
| `reasoning` | planner, fact-checker, critic | Nemotron 3.5 → Ernie 5.5 → Ling 3.2 → Groq gpt-oss-120b* |
| `worker` | researcher, writer | Ernie 5.5 → Nemotron 3.5 → Ling 3.2 → Groq gpt-oss-20b* |
| `judge` | evaluation only | Ling 3.2 → Nemotron 3.5 |

\* Groq joins only when `GROQ_API_KEY` is set. `RS_GROQ_POSITION=last` (default) makes it the rescue model, and `first` makes it primary (sensible on a paid Groq tier). Any chain can be overridden with an env var, e.g. `RS_WORKER_MODELS="openrouter:a/b:free, groq:c"`.

## The factory: `LLMFactory`

- `make_chat_model(spec, settings)` creates `ChatOpenRouter` or `ChatGroq`. Gotcha from notebook 01: `ChatOpenRouter`'s timeout is in **milliseconds**, so the factory converts seconds to ms.
- `chat(role)`: a plain chat runnable with fallbacks (used by the writer).
- `structured(schema, role)`: applies `with_structured_output(schema)` **to each model first, then chains them** (wrapping a fallback chain with structured output is fragile, notebook 02). On Groq it uses `method="json_schema"` (see note 17).
- `invoke_structured(schema, role, messages)`: the **repair loop**. If the output fails validation, it appends "Your previous answer did not match the schema: <error>" and tries again, up to 2 times.
- `with_fallbacks(primary, backups)`: our own fallback runner. It tries each model in order. If every model fails and any failure is a quota or transient error, it raises `AllModelsFailedError` listing **all** failures, so a quota stop is recognised correctly. (LangChain's built-in version only re-raises the *first* error, which hid our quota problems; see note 17.)

## Retries

- OpenRouter: `llm_max_retries=1`, low on purpose: fail fast and let the next model take over.
- Groq: `groq_max_retries=4`. Its per-minute token limits clear within seconds and its SDK waits for the `retry-after` time.
- Graph level: `RetryPolicy` with `retry_on=is_retryable` (note 08).

## Structured output: why and how

LLMs naturally return text. We need **data** (a plan with a list of sub-questions, scores as integers). `with_structured_output(PydanticModel)` makes the model return JSON matching the schema, which is then validated into a Python object. Two methods:
- **tool / function calling**: the schema is presented as a "tool" the model calls. This is the default for OpenRouter models.
- **json_schema**: the provider constrains the output to the JSON schema. We use it for Groq.

## Groq vs OpenRouter (free tiers)

| | OpenRouter free | Groq free |
|---|---|---|
| Requests | ~50/day total | 1,000/day per model |
| Tokens | — | **8,000/minute per model** |
| Speed | 2–40 s per call | ~1–2 s per call |
| Best use here | Main provider | Rescue model (one researcher call ≈ 5k tokens, so parallel researchers overflow 8k TPM) |
