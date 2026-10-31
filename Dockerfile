FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim@sha256:637619278855a77885a94312efa7decd8479ca6cec5f959e134cbab96582821e

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
# Use the base image's Python: a downloaded one would land under /root, which appuser can't read
ENV UV_PYTHON_DOWNLOADS=0

# Dependencies first, so code changes don't invalidate this layer
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# UV_COMPILE_BYTECODE only covers installed packages, and appuser can't write __pycache__ here at runtime
RUN .venv/bin/python -m compileall -q app migrations

# /app stays root-owned: the app never writes to it, and a chown would duplicate the venv in a new layer
RUN useradd --system --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

# Call alembic/uvicorn from the venv directly; `uv run` would re-check the lock at startup
ENV PATH="/app/.venv/bin:$PATH"
# Loopback by default, since the server runs the image with --network host. Set UVICORN_HOST=0.0.0.0
# to publish the port with -p instead. uvicorn trusts X-Forwarded-* only from FORWARDED_ALLOW_IPS,
# which is nginx on loopback.
ENV UVICORN_HOST=127.0.0.1 \
    UVICORN_PORT=5300 \
    FORWARDED_ALLOW_IPS=127.0.0.1 \
    JSON_LOGS=true

EXPOSE 5300

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app"]
