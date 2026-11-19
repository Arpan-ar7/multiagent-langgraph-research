# One image for both services (API and UI); docker-compose.yml picks the command.
#
#   docker build -t research-system .
#   docker run --env-file .env -p 8000:8000 research-system            # API only
#   docker compose up                                                  # API + UI

# ---------------------------------------------------------------- build stage
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies first (cached layer; only re-run when the lockfile changes).
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Then the project itself. It stays an editable install, so `settings.PROJECT_ROOT`
# resolves to /app (data/, reports/ and ui/ live next to src/).
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------- runtime stage
FROM python:3.13-slim

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=builder --chown=app:app /app /app
COPY --chown=app:app ui ./ui
RUN mkdir -p data reports && chown app:app data reports

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    RS_DATA_DIR=/app/data \
    RS_REPORTS_DIR=/app/reports \
    RS_CHECKPOINT_DB=/app/data/checkpoints.sqlite \
    RS_API_HOST=0.0.0.0 \
    RS_API_PORT=8000 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

USER app
VOLUME ["/app/data", "/app/reports"]
EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["research-api"]
