#!/usr/bin/env bash
# S56 operator maintenance control (thin wrapper over the application seam).
#
# Maintenance state itself is a file OUTSIDE either database so it survives
# the replacement: $X_INSIGHT_MAINTENANCE_FILE or backend/var/maintenance.json.
# The application enters maintenance automatically on POST /restores/commit
# and leaves it only via POST /restores/{id}/reopen after health passes.
# This script only inspects that state and exercises the public HTTP seam;
# it never edits the database directly.
set -euo pipefail

BASE_URL="${X_INSIGHT_BASE_URL:-http://localhost:8000}"
MAINT_FILE="${X_INSIGHT_MAINTENANCE_FILE:-backend/var/maintenance.json}"

usage() {
  echo "usage: maintenance.sh [status]"
  echo "  status  print maintenance file state + /ready health (default)"
}

if [ "${1:-status}" != "status" ]; then
  usage >&2
  exit 2
fi

echo "--- maintenance file: ${MAINT_FILE} ---"
if [ -f "${MAINT_FILE}" ]; then
  cat "${MAINT_FILE}"
  echo
else
  echo '{"active": false}'
fi
echo "--- GET /api/v1/ready ---"
curl -fsS "${BASE_URL}/api/v1/ready" || echo "(ready endpoint unreachable)"
echo
echo "note: enter via POST /api/v1/restores/commit (admin, exact digest);"
echo "      exit only via POST /api/v1/restores/{id}/reopen after health passes."
