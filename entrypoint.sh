#!/bin/sh
set -e
uv run --no-dev alembic upgrade head
exec "$@"
