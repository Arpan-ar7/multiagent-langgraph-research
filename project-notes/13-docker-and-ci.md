# 13 · Docker and CI (Phase 5)

Status: ✅ files written and statically validated (`docker compose config` passes); 🟡 the image has **not been built yet**. Docker Desktop on this PC cannot start its engine because **WSL2 is not installed**, and the repo has no GitHub remote yet, so CI has not run.

## Dockerfile: one image, two uses (ADR 0005)

Multi-stage build:
1. **Builder stage** (`python:3.13-slim` + `uv`):
   - copy `pyproject.toml` + `uv.lock` → `uv sync --frozen --no-dev --no-install-project` (dependencies get their own cached layer, re-run only when the lockfile changes)
   - copy `src/` → `uv sync` again to install the project itself
2. **Runtime stage** (`python:3.13-slim`): copies the built `/app`, adds `ui/`, runs as a **non-root** user (uid 1000), and sets paths via env (`RS_DATA_DIR`, `RS_CHECKPOINT_DB`, `RS_API_HOST=0.0.0.0`).
   - `HEALTHCHECK` calls `/health`
   - default command: `research-api`

API keys are **never** in the image. `.dockerignore` excludes `.env`, data, notebooks, tests and caches; keys are passed at runtime.

## docker-compose.yml: API + UI

```bash
cp .env.example .env        # add keys
docker compose up --build   # API :8000, UI http://localhost:8501
```

- `api` builds the image and runs `research-api`. Checkpoints and the LLM cache live in the named volume `research-data`; reports go to `./reports`.
- `ui` reuses the same image (`pull_policy: never`) and runs Streamlit. It waits until the API is healthy, then reaches it at `http://api:8000`.
- On Linux hosts, `./reports` must be writable by uid 1000.

## CI: `.github/workflows/ci.yml`

On every push to `main` and every pull request:

**Job 1 · checks**
`uv sync --locked` → `ruff check` → `ruff format --check` → `mypy src ui` → `pytest -m "not live"`. No API keys needed, and tracing is off.

**Job 2 · docker** (after checks pass)
Build the image (with a GitHub Actions cache) → validate the compose file → `docker compose up --wait` → `curl` the API `/health` and the UI `/_stcore/health` → print logs on failure → tear down.

## To finish this phase

1. Install WSL2 (admin PowerShell: `wsl --install`, then restart) → start Docker Desktop → `docker compose up --build` → open http://localhost:8501.
2. Create a GitHub repo, `git remote add origin ...`, `git push -u origin main` → watch the Actions tab → add a CI badge to the README.
3. Optional deployment: Render / Hugging Face Spaces (Docker) or Streamlit Community Cloud.
