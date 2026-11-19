# 12 · Testing and code quality

Status: ✅ **87 tests pass** (`uv run pytest`, ~27 s, no network, no API keys), plus 3 live tests that are skipped by default.

## How we test an LLM system without calling LLMs

**Dependency injection.** The graph receives an `Agents` container (`agents/base.py`) of plain callables. Tests pass **stub agents** (`tests/conftest.py`) that return fixed `ResearchPlan`s, `Finding`s, etc. So the **real compiled graph** (routing, parallel `Send`, reducers, checkpoints, interrupts, error handlers) is tested deterministically, for free, in seconds.

## Test layers

| Folder | What | Examples |
|---|---|---|
| `tests/unit/` | Small pieces in isolation | schema validation; settings parsing; tools never raise; citation numbering/validation; retry and quota classification; LLM factory (timeout units, repair loop, Groq JSON-schema mode, retry budget); fallback chain errors; eval runner (resume, judge failure, LangSmith feedback); UI timeline |
| `tests/integration/` | The real graph and API with stubs | parallel research; a failed researcher; the critic loop; plan review pause/resume; **crash and resume from SQLite**; API endpoints and SSE; UI view model |
| `tests/live/` | Real APIs (`uv run pytest -m live`) | smoke tests that use quota |

Settings in `pyproject.toml`: `addopts = "-m 'not live'"` skips live tests; `filterwarnings = ["error::UserWarning"]` turns Pydantic serializer warnings into failures (they signal invalid models).

## Quality tools

```bash
uv run ruff check .            # lint (pycodestyle, pyflakes, isort, naming, pyupgrade, bugbear, simplify, ruff rules)
uv run ruff format --check .   # formatting
uv run mypy src ui             # strict static typing
uv run pytest                  # tests
```

- **mypy strict** caught real bugs, e.g. stub parameter names that did not match the agent `Protocol`s (keyword callers would break).
- **pre-commit** runs ruff and nbstripout on each commit.
- **CI** runs all of these on every push (note 13).
