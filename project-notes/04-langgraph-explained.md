# 04 · LangGraph explained with our graph

File: `src/research_system/graph/builder.py` (state in `graph/state.py`). Status: ✅ (covered by `tests/integration/test_graph.py`).

LangGraph lets you describe a workflow as a **graph**: boxes (nodes) that do work, arrows (edges) that say what runs next, and one shared **state** that flows through it. LangGraph then runs it, in parallel where possible, saving the state after each step.

## 1. State: the shared notebook all agents write into

```python
class ResearchState(TypedDict, total=False):
    query: str
    options: dict[str, Any]  # run options, saved with the run
    plan: ResearchPlan
    findings: Annotated[list[Finding], operator.add]  # ← reducer
    failures: Annotated[list[str], operator.add]
    warnings: Annotated[list[str], operator.add]
    metrics: Annotated[list[dict[str, Any]], operator.add]
    fact_check: FactCheckReport
    draft: Draft
    critique: Critique
    iteration: int
    report: str
```

- A node **returns only the keys it changed** (a "partial update"). LangGraph merges it into the state.
- **Reducers:** normally a new value *replaces* the old one. With `Annotated[list, operator.add]`, new lists are **appended**. This matters because 3 researchers finish at the same time and each returns `{"findings": [one_finding]}`. With `operator.add` we get all three; without it, they would conflict.

## 2. Nodes: plain Python functions

```python
def writer(state: ResearchState) -> dict[str, Any]:
    _emit("writer", "writing")  # progress event for the UI
    draft = agents.write(state["plan"], state["fact_check"])
    return {"draft": draft, "metrics": [_metric("writer", t0)]}


g = StateGraph(ResearchState)
g.add_node("writer", writer, retry_policy=LLM_RETRY)
```

Every node is a thin wrapper: **read state → call an injected agent → return a partial update**. The agent comes from the `Agents` container (dependency injection), so tests can pass in fake agents. Our nodes: `planner`, `human_review`, `researcher`, `fact_checker`, `writer`, `critic`, `finalize`.

## 3. Edges: fixed arrows

```python
g.add_edge(START, "planner")
g.add_edge("planner", "human_review")
g.add_edge("researcher", "fact_checker")
g.add_edge("fact_checker", "writer")
g.add_edge("writer", "critic")
g.add_edge("finalize", END)
```

## 4. Conditional edges and `Send`: parallel fan-out

After human review we start **one researcher per sub-question, all at once**:

```python
def dispatch_researchers(state) -> list[Send]:
    return [task(state, q.question, q.search_strategy) for q in state["plan"].sub_questions]


g.add_conditional_edges("human_review", dispatch_researchers, ["researcher"])
```

- A conditional edge is a function that decides where to go next.
- Returning a list of **`Send("researcher", payload)`** objects runs the `researcher` node **once per Send, in parallel**, each with its own private payload (`ResearcherTask`: sub-question, strategy, tool-call limit) instead of the whole state. This is LangGraph's **map-reduce**.
- When all researchers finish, their findings are merged by the reducer and the graph continues to `fact_checker` (it waits for all of them: a "superstep").

## 5. The critic loop (a bounded cycle)

```python
def after_critic(state) -> str | list[Send]:
    o = opts(state)
    if (
        critique.approved(o.approval_threshold)
        or state["iteration"] >= o.max_iterations
        or not critique.follow_up_questions
    ):
        return "finalize"
    return [task(state, q, "web") for q in critique.follow_up_questions]  # new research round


g.add_conditional_edges("critic", after_critic, ["researcher", "finalize"])
```

The graph has a **cycle** (critic → researcher → … → critic). It is safe because `max_iterations` (default 2) and LangGraph's `recursion_limit` (50) bound it.

## 6. `interrupt`: human in the loop

```python
def human_review(state):
    if not opts(state).human_review:
        return {}
    decision = interrupt({"objective": ..., "sub_questions": [...]})   # ← run pauses here
    ...keep only the selected sub-questions...
```

`interrupt()` stops the run and saves it. Later, `graph.stream(Command(resume={"sub_questions": [...]}), config)` continues from exactly that line, with the human's answer as the return value. Needs a checkpointer.

## 7. Checkpointer: save after every step

```python
checkpointer = SqliteSaver(sqlite3.connect(path), serde=safe_serializer())
graph = g.compile(checkpointer=checkpointer)
graph.stream(payload, {"configurable": {"thread_id": "20261119-..."}})
```

- Every run has a **thread_id**. After each step the state is written to `data/checkpoints.sqlite`.
- That gives us: **resume after a crash** (finished nodes are not re-run), **human-in-the-loop**, **run history** in the UI, and inspection with `graph.get_state(config)`.
- The serializer only allows our own schema classes to be loaded back (no arbitrary Python objects): a security choice.

## 8. Retry policies and error handlers

```python
LLM_RETRY = RetryPolicy(
    max_attempts=3, initial_interval=2.0, backoff_factor=2.0, retry_on=is_retryable
)
g.add_node("fact_checker", fact_checker, retry_policy=LLM_RETRY, error_handler=fact_check_failed)
g.add_node("critic", critic, retry_policy=LLM_RETRY, error_handler=critic_failed)
```

- `retry_on=is_retryable`: retry rate limits, 5xx and network errors, but **never** an exhausted daily quota (pointless).
- `error_handler`: if the fact-checker still fails, skip it (pass claims through with a warning) and `goto="writer"`. If the critic fails, finalize without review.
- Gotcha found in notebook 05: error handlers **do not apply to `Send` tasks**, so the researcher catches its own errors and returns a `failures` entry instead.

## 9. Streaming progress

Nodes call `get_stream_writer()({"agent": "writer", "status": "writing"})`. With `stream_mode=["custom", "updates"]` the service receives these events live and forwards them to the CLI, API (SSE) and UI timeline.

## The full picture

```
START → planner → human_review ─(Send ×N)→ researcher → fact_checker → writer → critic
                                              ▲                                   │
                                              └──── follow-ups (Send ×k) ◄────────┤
                                                                     approved/limit → finalize → END
```
