FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim@sha256:637619278855a77885a94312efa7decd8479ca6cec5f959e134cbab96582821e

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Dependencies first, so code changes don't invalidate this layer
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# /app stays root-owned: the app never writes to it, and a chown would duplicate the venv in a new layer
RUN useradd --system --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

# Call alembic/uvicorn from the venv directly; `uv run` would re-check the lock at startup
ENV PATH="/app/.venv/bin:$PATH"
# Defaults only: the server's --env-file overrides UVICORN_HOST to bind to loopback
ENV UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=5300 \
    JSON_LOGS=true

EXPOSE 5300

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--proxy-headers"]
