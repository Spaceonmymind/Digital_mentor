#!/bin/sh
set -eu

if [ "${1:-}" = "" ]; then
  echo "Usage: scripts/restore.sh backups/YYYYMMDD-HHMMSS" >&2
  exit 2
fi

backup_dir="$1"
test -f "$backup_dir/postgres.sql"
test -f "$backup_dir/reports.tar.gz"

docker compose exec -T db psql -U "${POSTGRES_USER:-digital_mentor}" "${POSTGRES_DB:-digital_mentor}" < "$backup_dir/postgres.sql"
tar -xzf "$backup_dir/reports.tar.gz"
