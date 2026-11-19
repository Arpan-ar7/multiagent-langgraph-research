# Project Notes: Multi-Agent AI Research System

> 📍 Entry point for the whole repo: [docs/START-HERE.md](../docs/START-HERE.md) (the reading order across the notes, docs and code).

These notes explain the whole project **from the basics**: what we are building, why, how every part works, which file does what, what is finished, and what is left.
They are written for learning, revision and interview preparation. The main `README.md` is the short public overview; these notes are the long version.

> Last updated: 2026-11-19 · Status: Phases 0–5 built · 87 automated tests passing · mypy strict clean

## Reading order

| # | Note | What you learn |
|---|---|---|
| 01 | [What we are building and why](01-what-and-why.md) | The problem, the idea, one run explained step by step |
| 02 | [Tech stack](02-tech-stack.md) | Every library and service, why we chose it, where it is used |
| 03 | [Project structure](03-project-structure.md) | Every folder and file, its job, and its status |
| 04 | [LangGraph explained with our graph](04-langgraph-explained.md) | State, reducers, nodes, edges, `Send`, `interrupt`, checkpoints |
| 05 | [The five agents](05-agents.md) | Planner, researcher, fact-checker, writer, critic: input → output |
| 06 | [Tools and search](06-tools-and-search.md) | Tavily, DuckDuckGo, arXiv, Wikipedia, and the tool design rules |
| 07 | [Models, fallbacks and structured output](07-models-and-fallbacks.md) | LLM factory, role chains, Groq/OpenRouter, repair loop |
| 08 | [Reliability: errors, retries, resume](08-reliability.md) | What happens when things fail, and why runs can always resume |
| 09 | [Citations and fact-checking](09-citations-and-trust.md) | How we make sure every citation is real |
| 10 | [Service, CLI, API and UI](10-service-cli-api-ui.md) | How users run the system: terminal, HTTP API, web UI |
| 11 | [Evaluation](11-evaluation.md) | How we measure quality: metrics, LLM-as-judge, LangSmith |
| 12 | [Testing and code quality](12-testing-and-quality.md) | Unit/integration tests with stub agents, ruff, mypy |
| 13 | [Docker and CI](13-docker-and-ci.md) | Container image, docker compose, GitHub Actions |
| 14 | [Notebook journey (Phase 1)](14-notebooks-journey.md) | What each experiment notebook taught us |
| 15 | [Status: done and left](15-status-done-and-left.md) | The full checklist of what is finished and what remains |
| 16 | [How to run everything](16-how-to-run.md) | Copy-paste commands |
| 17 | [Bugs found and lessons learned](17-bugs-and-lessons.md) | Real problems we hit and how we fixed them |
| 18 | [Interview talking points](18-interview-talking-points.md) | How to explain this project on a resume and in interviews |

## The project in one paragraph

You ask a research question. A **planner** agent splits it into 3–5 focused sub-questions. Several **researcher** agents then search the web, arXiv and Wikipedia **at the same time**, each returning claims tied to the URLs they actually read. A **fact-checker** throws out claims citing URLs that were never retrieved, scores source credibility and finds contradictions. A **writer** turns the verified claims into a Markdown report with `[n]` citations, and a **critic** grades it. If the critic finds gaps, new research rounds run automatically (a bounded loop). Everything is orchestrated by **LangGraph** and saved to SQLite after every step, so a crashed run continues where it stopped. You can use it from the terminal, through a FastAPI streaming API, or in a Streamlit web UI.

## Legend used in these notes

- ✅ done and verified
- 🟡 done but partly verified, or waiting on something (quota, setup)
- ⏳ not done yet
