# 18 · Interview talking points

## 30-second pitch

"I built a multi-agent research system with LangGraph. A planner splits a question into sub-questions, parallel researcher agents search the web and arXiv using LangGraph's `Send` API, a fact-checker verifies that every citation points to a page that was actually retrieved, a writer produces a cited report, and a critic grades it and triggers more research when there are gaps. It checkpoints every step to SQLite so crashed runs resume, supports human approval of the plan, streams progress through a FastAPI SSE API to a Streamlit UI, and is measured with an evaluation harness using LLM-as-judge and LangSmith."

## Resume bullets (fill in final numbers after the benchmark)

- Built a LangGraph multi-agent research system (planner, parallel researchers, fact-checker, writer, critic) using `Send` map-reduce for concurrent research (in notebook 05, five 1-second tasks finished in 1.01 s; measure the real speed-up on a healthy-quota run of notebook 07 and put it here).
- Guaranteed citation integrity: code-built references and URL grounding checks (grounding rate 1.00 on the first real benchmark run), with a critic feedback loop for gaps.
- Engineered resilience on free-tier LLMs: role-based model fallback chains, quota-aware retry classification, graceful degradation, and SQLite-checkpointed resume.
- Shipped a FastAPI SSE backend (background runs, replayable events, human-in-the-loop plan approval) and a Streamlit UI; 87 tests, strict mypy, Docker and GitHub Actions CI.

## Likely questions and good answers

**Why LangGraph and not a simple agent loop?**
I needed parallel workers, a bounded loop, persistent state, human pauses and streaming. LangGraph gives all of them as first-class features (`Send`, conditional edges, checkpointer, `interrupt`, stream modes) with explicit, testable control flow. See ADR 0001.

**How do you stop hallucinated citations?**
The LLM never writes URLs. Tools return URL lines, code records retrieved URLs, claims citing unretrieved URLs are dropped, the writer only uses `[n]` markers, and code builds and validates the references.

**How do you test something non-deterministic?**
Dependency injection: the graph depends on agent interfaces, so integration tests run the *real* graph with deterministic stubs (parallelism, loop, failures, crash-resume) in seconds with no API calls. Quality is measured separately with the eval harness.

**What happens when a model or API fails?**
A fallback chain per role; retries only for transient errors; no retries for exhausted quotas; failed researchers are recorded and listed in Limitations; a failed fact-checker or critic degrades gracefully; and everything is checkpointed for resume.

**Hardest bug?**
The quota stop hidden behind a Groq 404: LangChain's fallback wrapper re-raises the first error. I found it in the first real benchmark run, reproduced it, wrote a fallback runner that surfaces all failures, and added regression tests (note 17).

**Why is approval decided by code?**
LLMs are inconsistent at yes/no judgements about their own work. The critic only scores against a rubric; a threshold in code decides. It is predictable and tunable.

**What would you do next?**
Finish the benchmark with paid credits, add a cost-aware model router, Semantic Scholar for citation counts, a local PDF/RAG agent, and expose the system as an MCP server.
