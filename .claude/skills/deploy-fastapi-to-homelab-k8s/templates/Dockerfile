# Single-container image: build the React SPA with bun, then serve it same-origin
# from the FastAPI backend (API under /api/v1). Build context is the repo root.

# ── Stage 1: build the React SPA ────────────────────────────────────────────
FROM oven/bun:1 AS frontend-build
WORKDIR /app
COPY package.json bun.lock /app/
COPY frontend/package.json /app/frontend/
WORKDIR /app/frontend
RUN bun install
COPY ./frontend /app/frontend
# Empty base URL => the generated client calls /api/v1 on this same origin.
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN bun run build

# ── Stage 2: FastAPI backend that also serves the built SPA ─────────────────
FROM python:3.14
ENV PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
WORKDIR /app/
ENV PATH="/app/.venv/bin:$PATH"

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-workspace --package app

COPY ./backend/scripts /app/backend/scripts
COPY ./backend/pyproject.toml ./backend/alembic.ini /app/backend/
COPY ./backend/app /app/backend/app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --package app

# Bundle the built SPA so FastAPI serves it same-origin (backend/static).
COPY --from=frontend-build /app/frontend/dist /app/backend/static

WORKDIR /app/backend/
EXPOSE 8000
CMD ["bash", "scripts/start.sh"]
