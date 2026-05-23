# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS builder
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libcairo2-dev libpango-1.0-0 libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src

FROM python:3.12-slim-bookworm AS runtime
# WeasyPrint runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 \
    shared-mime-info fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/* && useradd -r -u 1000 app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src /app/src
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/health || exit 1
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY:-2}"]
