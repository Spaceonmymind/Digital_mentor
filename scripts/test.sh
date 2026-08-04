#!/bin/sh
set -eu

cd "$(dirname "$0")/../backend"
../.venv/bin/python -m pytest
cd ..
node frontend/tests/smoke.mjs
