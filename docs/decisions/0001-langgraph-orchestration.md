# ADR 0001: Use LangGraph for multi-agent orchestration

**Status:** Accepted

## Context
The system needs parallel workers, conditional loops (critic → re-research), persistent state, human-in-the-loop pauses and streaming progress to a UI.

## Decision
Orchestrate the agents as a LangGraph `StateGraph`: a shared typed state with reducers, `Send` fan-out for parallel researchers, researcher subgraphs, a SQLite checkpointer, and `interrupt()` for plan approval.

## Consequences
- Explicit, inspectable control flow that can be tested node by node.
- Checkpointing gives resume, time-travel debugging and human-in-the-loop for free.
- More upfront design than a single ReAct agent, which is acceptable for this project.
