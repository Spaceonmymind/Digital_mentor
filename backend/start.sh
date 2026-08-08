#!/bin/sh
set -eu

attempt=1
until alembic upgrade head; do
  if [ "$attempt" -ge 15 ]; then
    echo "Alembic migration failed after $attempt attempts" >&2
    exit 1
  fi
  echo "Database is not ready for migration, retry $attempt" >&2
  attempt=$((attempt + 1))
  sleep 2
done

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
