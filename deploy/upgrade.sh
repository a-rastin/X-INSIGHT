#!/usr/bin/env bash
# S57 upgrade path (production, localhost/disposable target only).
#
# Steps: 1) backup-before-upgrade via POST /api/v1/backups (T10),
#        2) build/pull pinned images, 3) explicit `alembic upgrade head`,
#        4) restart app/worker/edge.
#
# On migration failure: abort BEFORE the container switch, leave the old
# containers running, and print the recovery pointer to deploy/OPERATIONS.md
# ("Migration-failure recovery"). Never wipes volumes (no volume deletion,
# no database reset). Never deploys to an external host: BASE_URL must stay
# localhost/127.0.0.1; the compose file is the local deploy/compose.prod.yaml.
#
# Usage: ./deploy/upgrade.sh [cookie-jar]
#   Login first: POST /api/v1/auth/login (admin) with curl -c <cookie-jar>.
#   Requires: docker compose, backend toolchain (uv), admin session cookie.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/deploy/compose.prod.yaml"
BASE_URL="${X_INSIGHT_BASE_URL:-http://localhost:8000}"
COOKIE_JAR="${1:-/tmp/xinsight-upgrade-cookies.txt}"

case "${BASE_URL}" in
  http://localhost*|http://127.0.0.1*)
    ;;
  *)
    echo "refusing: X_INSIGHT_BASE_URL must stay localhost/127.0.0.1 (got ${BASE_URL})" >&2
    echo "recovery: see deploy/OPERATIONS.md (localhost/disposable target only)" >&2
    exit 2
    ;;
esac

if [ ! -f "${COOKIE_JAR}" ]; then
  echo "missing admin session cookie jar: ${COOKIE_JAR}" >&2
  echo "login first: curl -c ${COOKIE_JAR} -X POST ${BASE_URL}/api/v1/auth/login ..." >&2
  echo "then rerun: ./deploy/upgrade.sh ${COOKIE_JAR}" >&2
  exit 2
fi

echo "=== step 1/4: backup-before-upgrade (POST /api/v1/backups) ==="
IDEMPOTENCY_KEY="$(cat /proc/sys/kernel/random/uuid)"
CREATE_RESP="$(curl -fsS -b "${COOKIE_JAR}" -X POST "${BASE_URL}/api/v1/backups" \
  -H "Idempotency-Key: ${IDEMPOTENCY_KEY}" \
  -H "Content-Type: application/json" -d '{}')"
JOB_ID="$(printf '%s' "${CREATE_RESP}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')"
echo "backup job: ${JOB_ID}"
BACKUP_OK=0
for _ in $(seq 1 60); do
  STATUS="$(curl -fsS -b "${COOKIE_JAR}" "${BASE_URL}/api/v1/backups/${JOB_ID}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  echo "backup status: ${STATUS}"
  if [ "${STATUS}" = "succeeded" ]; then
    BACKUP_OK=1
    break
  fi
  if [ "${STATUS}" = "failed" ]; then
    echo "backup job failed; aborting upgrade before any image/migration change" >&2
    exit 1
  fi
  sleep 5
done
if [ "${BACKUP_OK}" != "1" ]; then
  echo "backup did not reach succeeded; aborting upgrade" >&2
  exit 1
fi
echo "backup succeeded: ${JOB_ID}"

echo "=== step 2/4: build/pull pinned images + rebuild web bundle ==="
docker compose -f "${COMPOSE_FILE}" build --pull
docker compose -f "${COMPOSE_FILE}" pull
cd "${REPO_ROOT}/web"
npm ci
npm run build
test -f "${REPO_ROOT}/web/dist/index.html"
cd "${REPO_ROOT}/backend"

echo "=== step 3/4: explicit migration (alembic upgrade head) ==="
cd "${REPO_ROOT}/backend"
uv sync --locked --no-dev --no-install-project
if ! uv run alembic upgrade head; then
  echo "migration failed; old containers still running (no switch performed)" >&2
  echo "recovery: see deploy/OPERATIONS.md section 'Migration-failure recovery'" >&2
  echo "  fix-forward (rerun upgrade head) vs restore-from-backup (recovery-runbook.md)" >&2
  exit 1
fi

echo "=== step 4/4: restart app/worker/edge ==="
docker compose -f "${COMPOSE_FILE}" up -d app worker edge
echo "upgrade complete. Verify: GET ${BASE_URL}/api/v1/ready and chart reads."
