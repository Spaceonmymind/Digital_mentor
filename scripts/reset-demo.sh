#!/bin/sh
set -eu

docker compose down -v
find storage/documents -type f ! -name .gitkeep -delete
find storage/extracted -mindepth 1 ! -name .gitkeep -exec rm -rf {} +
find storage/reports -mindepth 1 ! -name .gitkeep -exec rm -rf {} +
find storage/audio -mindepth 1 -exec rm -rf {} + 2>/dev/null || true
