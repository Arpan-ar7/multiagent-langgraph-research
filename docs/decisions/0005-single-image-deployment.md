# ADR 0005: One container image for API and UI

**Status:** Accepted

## Context
The API and the Streamlit UI share the same package (`research_system`): the UI imports the typed client and the timeline view model.

## Decision
- One multi-stage `Dockerfile`: `uv sync --frozen --no-dev` in a builder stage (dependencies cached separately from source), copied into a slim runtime stage that runs as a non-root user with a healthcheck.
- `docker-compose.yml` runs the same image twice with different commands. The UI waits for the API to be healthy and reaches it at `http://api:8000`.
- API keys come from `.env` at runtime and are excluded from the build context (`.dockerignore`). Checkpoints and the LLM cache live in a named volume, and reports in a bind mount.
- CI builds the image and starts the compose stack, checking both health endpoints without any keys.

## Consequences
- One build, one version, with no drift between the API and the UI.
- The UI image carries the agent dependencies it does not need (larger image, simpler pipeline).
- On Linux hosts, the `./reports` bind mount must be writable by UID 1000 (the container user).
