#!/bin/sh
set -eu

timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="backups/$timestamp"
mkdir -p "$backup_dir"

docker compose exec -T db pg_dump -U "${POSTGRES_USER:-digital_mentor}" "${POSTGRES_DB:-digital_mentor}" > "$backup_dir/postgres.sql"
tar -czf "$backup_dir/reports.tar.gz" storage/reports

echo "$backup_dir"
