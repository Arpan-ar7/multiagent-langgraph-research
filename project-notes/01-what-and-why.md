# 01 · What we are building and why

## The problem

A normal chatbot answers from memory. That gives three problems for research questions:

1. **Out of date:** the model does not know what happened after its training.
2. **Hallucinations:** it can invent facts and even invent URLs that look real.
3. **Shallow:** one answer in one pass, with no checking and no second look.

A basic **RAG** app (retrieve, then generate) fixes problem 1, but it is still a single LLM call: no planning, no verification, no self-review.

## Our idea: a team of agents

We copy how a human research team works:

| Human team | Our system |
|---|---|
| Lead splits the topic into questions | **Planner** agent |
| Several analysts research in parallel | **Researcher** agents (run at the same time) |
| Someone checks the sources | **Fact-checker** agent |
| Someone writes the report | **Writer** agent |
| Editor reviews it and asks for more work | **Critic** agent (can trigger more research) |

An **agent** here is simply an LLM call (or a small LLM loop with tools) with one clear job, a prompt, and a typed output.
The agents never call each other. They communicate only through a shared **state** that LangGraph passes between them (see note 04).

## One run, step by step

Example: `uv run research "What is the LangGraph Send API used for?"`

1. **Planner** (`agents/planner.py`): the LLM returns a `ResearchPlan`: an objective, a research type, 3–5 sub-questions (each with a search strategy: web, academic or encyclopedic) and a report outline.
2. **Human review** (optional, `--review`): the run **pauses** and shows you the plan. You can approve it or keep only some sub-questions. The pause survives restarts, because it is saved in the checkpoint.
3. **Researchers ×N in parallel** (`agents/researcher.py`): each one is a ReAct agent. It thinks, calls a search tool, reads the results, and repeats (with limits). It returns a `Finding`: a summary, 1–6 claims each with source URLs, a confidence level and gaps. Code (not the LLM) records which URLs were actually retrieved.
4. **Fact-checker** (`agents/fact_checker.py`): code checks that every cited URL was really retrieved ("grounding"), and rates each domain's credibility. Then one LLM call looks for contradictions between claims. Each claim becomes `supported`, `contested` or `unverified`.
5. **Writer** (`agents/writer.py`): it receives only usable claims, already numbered `[1]`, `[2]`... It writes Markdown and is told never to write URLs.
6. **Critic** (`agents/critic.py`): it scores coverage, evidence use and coherence from 1 to 5, and lists gaps and up to 3 follow-up questions. **Code** decides approval: all scores ≥ 4 (configurable).
7. **Loop or finish:** if the report is not approved, there are follow-up questions and rounds are left, the follow-ups go to new parallel researchers (back to step 3). Otherwise →
8. **Finalize** (`graph/builder.py` + `utils/citations.py`): code appends the References list, validates every `[n]` marker, and adds a "Limitations" section listing failed researchers or skipped steps. The report is saved to `reports/`.

The real run of this example (2026-11-19) produced a report with 2 real LangChain documentation references and critic scores coverage 4 / evidence 3 / coherence 5.

## The guiding principle

> **Code does what rules can decide; the LLM is used only for judgement.**

Examples: code numbers citations, builds references, checks URL grounding, decides approval, enforces limits. The LLM plans, searches, writes and judges quality. This makes the system cheaper, testable and much harder to fool.

## Why this is more than a chatbot

It **plans, works in parallel, verifies, critiques itself and iterates**. It tracks where each claim came from, recovers from failures, pauses for human approval, and is **measured** with an evaluation suite. See note 18 for how to present this.
