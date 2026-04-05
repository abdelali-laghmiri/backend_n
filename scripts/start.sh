#!/usr/bin/env sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  python -m alembic upgrade head
fi

exec python -m app.server
