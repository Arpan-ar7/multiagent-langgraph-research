# 11 · Evaluation: measuring quality

Files: `src/research_system/evals/`. Command: `uv run research-eval`. Status: ✅ harness built and verified in dry-run mode; 🟡 real results: 1 of 10 runs done (quota-limited).

## The question we answer

> Does the critic loop (`critic_loop`, up to 2 rounds) produce better reports than a single pass (`single_pass`, 1 round), and at what cost?

## Benchmark (`evals/dataset.py`): 5 question types

| Kind | Question |
|---|---|
| technical | Main techniques for reducing hallucinations in LLMs as of 2026 |
| comparative | LangGraph vs CrewAI vs AutoGen for multi-agent systems |
| trend | State of solid-state battery commercialization for EVs |
| factual | How RAG works and its common failure modes |
| exploratory | Effects of generative AI on developer employment and hiring |

The questions are also synced to the LangSmith dataset `research-system-benchmark` (idempotent).

## What is measured

**Deterministic metrics** (`evals/metrics.py`, from the run state): grounding rate, citation problems, sources cited, distinct domains, critic iterations, failed researchers, report words, LLM calls and tokens (via a callback counter that also works in parallel threads).

**LLM-as-judge** (`Judge`): relevance, completeness, specificity (1–5) plus a rationale. It runs on the separate `judge` model chain (Ling → Nemotron), so a model is not grading its own writing (self-preference bias).

**LangSmith:** each evaluated run gets a fixed `run_id`; the judge scores and metrics are attached to its trace as **feedback**.

## The runner is resumable (`evals/runner.py`)

- Each (config × question) pair runs on a stable thread id (`eval-<config>-<hash>`) in the checkpoint DB. A quota stop mid-run resumes mid-graph the next day.
- If only the judge fails, the finished report is reused next time.
- Results are appended to `data/eval_results.jsonl` as soon as each pair completes.
- `--max-runs N` caps a session to fit the daily quota.
- **Dry runs** (`--dry-run`) use stub agents, a separate checkpoint DB and a separate results file, so fake results can never mix with real ones.

## Results so far

| Pair | Relevance | Completeness | Specificity | Grounding | Sources / domains | LLM calls |
|---|---|---|---|---|---|---|
| single_pass × technical | 5 | 4 | 5 | 1.00 | 22 / 10 | 37 |

The critic_loop × technical run is partly checkpointed and will resume. A run costs ~37 calls, so the free tier (~50/day) fits about one run per day, and all 10 pairs need about 10 days, or one session with paid credits.

```bash
uv run research-eval --dry-run        # free pipeline check
uv run research-eval --max-runs 1     # one real pair per day on the free tier
uv run research-eval --summary        # table (also written to reports/evaluation.md)
```
