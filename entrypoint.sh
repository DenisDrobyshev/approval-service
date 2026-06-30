#!/usr/bin/env bash
set -euo pipefail

# Apply database migrations, then start the API server.
echo "[entrypoint] Running database migrations..."
alembic upgrade head

echo "[entrypoint] Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
