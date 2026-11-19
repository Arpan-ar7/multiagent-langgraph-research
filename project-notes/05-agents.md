# 05 · The five agents

All in `src/research_system/agents/`. Prompts in `prompts/templates.py`. Output schemas in `schemas/`. Status: ✅ all five, each tested with stubs and verified in real runs.

Every agent follows a `Protocol` in `agents/base.py`, so the graph only knows *call signatures*, never LLM details. `build_agents(settings)` in `agents/__init__.py` creates the real ones.

## 1. Planner: `planner.py`

| | |
|---|---|
| Input | the user's query |
| Output | `ResearchPlan`: objective, research type, 3–5 `SubQuestion`s (question, rationale, search strategy), report outline (3–7 headings) |
| Model role | reasoning |
| LLM does | decomposes the question |
| Code does | trims to `max_sub_questions`; validates uniqueness; plan edits go through `with_sub_questions()`, which re-validates |

The prompt includes today's date (models don't know it) and demands non-overlapping, searchable sub-questions.

## 2. Researcher: `researcher.py` (the only agent with tools)

| | |
|---|---|
| Input | one sub-question + strategy (web / academic / encyclopedic) + tool-call limit |
| Output | `Finding`: summary, 1–6 `Claim`s (statement + source URLs), confidence, gaps, `retrieved_urls` |
| Model role | worker |
| Built with | LangChain `create_agent` (a ReAct loop) |

How the ReAct loop works: the model sees the question and the tool list → decides to call e.g. `web_search("...")` → reads the result → maybe calls another tool → finally returns a structured `Finding` (via `ToolStrategy(Finding)`).

Middleware attached to the agent:
- `ModelFallbackMiddleware`: if the model errors, try the next one in the worker chain
- `ToolCallLimitMiddleware(run_limit=max_tool_calls)`: at most N tool calls (default 4)
- `ModelCallLimitMiddleware(run_limit=7)`: at most 7 LLM calls, so no runaway loops

Code does: `retrieved_urls` is filled **from the tool outputs**, never by the model. That is what makes grounding checks possible.

## 3. Fact-checker: `fact_checker.py`

| | |
|---|---|
| Input | all `Finding`s |
| Output | `FactCheckReport`: each claim as `VerifiedClaim` (status + credibility) + conflict explanations |
| Model role | reasoning (one call, only if ≥2 grounded claims) |

Steps:
1. **Grounding (code):** a claim is grounded only if *every* URL it cites is in its researcher's `retrieved_urls`. Invented URLs fail here.
2. **Credibility (code):** `utils/sources.py` scores domains: `.gov/.edu/arxiv/nature/acm/ieee` = 0.9, `wikipedia/github/reuters/...` = 0.7, others 0.5.
3. **Contradictions (LLM):** grounded claims are numbered and the LLM returns pairs that cannot both be true (`ConflictReport`).
4. Status: not grounded → `unverified` (dropped from the report); in a conflict → `contested`; otherwise `supported`.

## 4. Writer: `writer.py`

| | |
|---|---|
| Input | plan + fact-check report |
| Output | `Draft`: Markdown with `[n]` markers + the URL→number map |
| Model role | worker, temperature 0.3 |

Code first numbers the sources (`number_sources`). The writer sees evidence lines like `- (supported) Statement text [1][2]` and the outline. Rules: use only this evidence, cite with the markers, **never write URLs**, present contested claims as disputed, about 400–600 words, no references section (code adds it).

## 5. Critic: `critic.py`

| | |
|---|---|
| Input | plan + draft Markdown |
| Output | `Critique`: coverage, evidence_use, coherence (1–5), justification, gaps, ≤3 follow-up questions |
| Model role | reasoning |

**Code decides approval:** `Critique.approved(threshold)` = all three scores ≥ threshold (default 4). The LLM only scores. Follow-up questions become new researcher tasks if the report is not approved.

## Structured output everywhere

Every decision-making agent returns a **Pydantic model**, not free text. `Field(description=...)` texts are sent to the LLM as part of the schema, so they are written as instructions. If the output is invalid, `LLMFactory.invoke_structured` shows the model its validation error and asks again (up to 2 repairs). See note 07.
