#!/bin/sh
set -eu

python /app/docker/validate_env.py

if [ "${HMS_RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[medora] Applying Alembic migrations..."
    python -m flask --app run db upgrade
fi

echo "[medora] Starting application: $*"
exec "$@"
