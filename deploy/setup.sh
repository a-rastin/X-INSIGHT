#!/usr/bin/env bash
# S57 fresh-install migration entrypoint (production).
#
# Explicit, non-destructive: runs `alembic upgrade head` against the
# deployment database with locked dependencies. Fails loudly (nonzero exit
# via `set -e`) on any migration error. Never wipes the DB volume, never
# reseeds data, never touches disposable dev state. The dev-only
# `make migrate` target is untouched and remains the local-dev path.
#
# Usage: DATABASE_URL=postgresql://... ./deploy/setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}/backend"
uv sync --locked --no-dev --no-install-project
uv run alembic upgrade head

# Build the web bundle served by edge at `/` (bind-mounted as
# ../web/dist in deploy/compose.prod.yaml). Fails loudly if the build
# does not produce dist/index.html.
cd "${REPO_ROOT}/web"
npm ci
npm run build
test -f "${REPO_ROOT}/web/dist/index.html"
