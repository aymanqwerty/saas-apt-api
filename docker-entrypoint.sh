#!/usr/bin/env bash
set -euo pipefail

# Apply any pending database migrations before serving traffic.
# Safe to run on every boot: Alembic no-ops when already at head.
echo "Running database migrations..."
alembic upgrade head

echo "Starting API on port ${PORT:-8000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
