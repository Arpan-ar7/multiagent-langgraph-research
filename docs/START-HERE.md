# 👋 Start Here

**This is the first file to read.** It gives you the reading path through the whole project: what to open first, what to open next, and what each file teaches you.
Follow the steps in order. Each step links to the file and says why you are reading it.

> Project: a multi-agent AI research system built with LangGraph. You ask a question, and a team of AI agents plans the research, searches the web and papers in parallel, fact-checks the sources, writes a cited report and critiques it.

---

## Step 1 · Understand the project (≈ 15 min)

| # | Read | What it gives you |
|---|---|---|
| 1 | [README.md](../README.md) | The public overview: what the system does, the flow diagram, how to install and run it |
| 2 | [project-notes/README.md](../project-notes/README.md) | The index of the detailed notes and the one-paragraph summary |
| 3 | [01 · What we are building and why](../project-notes/01-what-and-why.md) | The problem, the agent team idea, and **one run explained step by step** |
| 4 | [02 · Tech stack](../project-notes/02-tech-stack.md) | Every library and service, why it was chosen, and where it is used |
| 5 | [03 · Project structure](../project-notes/03-project-structure.md) | Every folder and file, its job and its status: your map of the code |

## Step 2 · Learn how it works (≈ 45 min)

| # | Read | What it gives you |
|---|---|---|
| 6 | [04 · LangGraph explained](../project-notes/04-langgraph-explained.md) | **The core:** state, reducers, nodes, edges, parallel `Send`, the critic loop, `interrupt`, checkpoints, using our real graph code |
| 7 | [05 · The five agents](../project-notes/05-agents.md) | Planner, researcher, fact-checker, writer, critic: input → output, and what the LLM does vs. what code does |
| 8 | [06 · Tools and search](../project-notes/06-tools-and-search.md) | The researcher's 4 tools and the rules that make them safe |
| 9 | [07 · Models and fallbacks](../project-notes/07-models-and-fallbacks.md) | The LLM factory, model roles, fallback chains, structured output, Groq vs. OpenRouter |
| 10 | [08 · Reliability](../project-notes/08-reliability.md) | What happens when something fails, and how every run can resume |
| 11 | [09 · Citations and trust](../project-notes/09-citations-and-trust.md) | How we guarantee that every citation points to a page that was really read |
| 12 | [10 · Service, CLI, API and UI](../project-notes/10-service-cli-api-ui.md) | How users run it: terminal, FastAPI with live streaming, Streamlit UI |

## Step 3 · Read the real code in this order (≈ 1 h)

Open these alongside notes 04–10. The order follows the data flow.

| # | File | What to look for |
|---|---|---|
| 13 | [graph/state.py](../src/research_system/graph/state.py) | The shared state and the `operator.add` reducers |
| 14 | [graph/builder.py](../src/research_system/graph/builder.py) | **The whole graph**: nodes, edges, `Send` fan-out, the critic loop, retries, error handlers |
| 15 | [agents/base.py](../src/research_system/agents/base.py) | Agent interfaces and dependency injection |
| 16 | [agents/planner.py](../src/research_system/agents/planner.py) → [researcher.py](../src/research_system/agents/researcher.py) → [fact_checker.py](../src/research_system/agents/fact_checker.py) → [writer.py](../src/research_system/agents/writer.py) → [critic.py](../src/research_system/agents/critic.py) | The five agents in the order they run |
| 17 | [prompts/templates.py](../src/research_system/prompts/templates.py) | Every prompt |
| 18 | [schemas/](../src/research_system/schemas/) | The Pydantic output of every agent |
| 19 | [tools/research_tools.py](../src/research_system/tools/research_tools.py) | The tools the researcher calls |
| 20 | [config/llm.py](../src/research_system/config/llm.py) and [config/settings.py](../src/research_system/config/settings.py) | Model chains, fallbacks, the repair loop, all settings |
| 21 | [utils/citations.py](../src/research_system/utils/citations.py) | Code-built references and citation validation |
| 22 | [service.py](../src/research_system/service.py) | The single entry point used by the CLI, API and UI |
| 23 | [api/app.py](../src/research_system/api/app.py), [api/runs.py](../src/research_system/api/runs.py), [ui/streamlit_app.py](../ui/streamlit_app.py) | The API and the UI |

## Step 4 · Quality, evaluation and deployment (≈ 30 min)

| # | Read | What it gives you |
|---|---|---|
| 24 | [11 · Evaluation](../project-notes/11-evaluation.md) | How quality is measured: metrics, LLM-as-judge, LangSmith, results so far |
| 25 | [12 · Testing and quality](../project-notes/12-testing-and-quality.md) | How we test an LLM system without calling LLMs (stub agents) |
| 26 | [13 · Docker and CI](../project-notes/13-docker-and-ci.md) | The container image, docker compose, and the GitHub Actions pipeline |

## Step 5 · History, decisions and evidence (≈ 30 min)

| # | Read | What it gives you |
|---|---|---|
| 27 | [14 · Notebook journey](../project-notes/14-notebooks-journey.md) | What each experiment notebook (01–08) taught us |
| 28 | [experiments-log.md](experiments-log.md) | Every experiment finding and decision, with numbers |
| 29 | [architecture.md](architecture.md) | Architecture, the key design decisions table, the error-handling table |
| 30 | [decisions/](decisions/): [0001](decisions/0001-langgraph-orchestration.md) · [0002](decisions/0002-free-model-fallback-chains.md) · [0003](decisions/0003-background-runs-and-sse.md) · [0004](decisions/0004-code-built-citations.md) · [0005](decisions/0005-single-image-deployment.md) | Architecture Decision Records: why LangGraph, fallback chains, background runs + SSE, code-built citations, one Docker image |
| 31 | [17 · Bugs and lessons](../project-notes/17-bugs-and-lessons.md) | Real bugs we hit and how we fixed them |

## Step 6 · Use it and finish it

| # | Read | What it gives you |
|---|---|---|
| 32 | [16 · How to run everything](../project-notes/16-how-to-run.md) | Copy-paste commands: setup, CLI, UI, Docker, evaluation, checks, settings |
| 33 | [15 · Status: done and left](../project-notes/15-status-done-and-left.md) | **The checklist** of what is finished and what remains, with how to do each item |
| 34 | [18 · Interview talking points](../project-notes/18-interview-talking-points.md) | Pitch, resume bullets, likely interview questions with answers |

---

## Short on time?

- **10 minutes:** [README.md](../README.md) → [01](../project-notes/01-what-and-why.md) → [15](../project-notes/15-status-done-and-left.md)
- **Before an interview:** [01](../project-notes/01-what-and-why.md) → [04](../project-notes/04-langgraph-explained.md) → [17](../project-notes/17-bugs-and-lessons.md) → [18](../project-notes/18-interview-talking-points.md)
- **Want to run it now:** [16 · How to run](../project-notes/16-how-to-run.md)
