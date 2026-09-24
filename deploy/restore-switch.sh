#!/usr/bin/env bash
# S56 operator restore drill (disposable environment ONLY).
#
# Demonstrates the full replacement protocol through public HTTP seams:
# backup -> validate/stage -> commit (exact digest) -> verify -> reopen,
# with rollback evidence on injected failure. Never run against the owner's
# live database. The in-application switch is phased table replacement under
# a maintenance lock with deployment-generation fencing; PostgreSQL cannot
# transactionally combine a database switch and process restart, so this
# script performs explicit phases and checks each one.
#
# Required env: admin session via login first; pass cookies with curl -b/-c.
# See docs/dev/recovery-runbook.md for the full operator procedure.
set -euo pipefail

BASE_URL="${X_INSIGHT_BASE_URL:-http://localhost:8000}"
COOKIE_JAR="${1:-/tmp/xinsight-restore-cookies.txt}"

echo "1) create backup:      POST /api/v1/backups (Idempotency-Key, admin)"
echo "   poll:               GET  /api/v1/backups/{id} until succeeded"
echo "   download:           GET  /api/v1/backups/{id}/download"
echo "2) stage:              POST /api/v1/restores/validate (multipart field 'archive')"
echo "   inspect:            GET  /api/v1/restores/{id} (digest, impact, key-reentry note)"
echo "3) commit (exact digest only):"
echo "                       POST /api/v1/restores/commit {restore_id, confirmation_digest}"
echo "   effects: maintenance file active, generation +1, pre-restore backup job,"
echo "            phased table replacement, sessions/grants revoked,"
echo "            nonterminal runs/jobs cancelled, restore.commit audit + operator log."
echo "4) verify (while fenced): login works, GET /patients reads staged data,"
echo "   GET /restores/{id} committed, writes still 503 MAINTENANCE."
echo "5) reopen:             POST /api/v1/restores/{id}/reopen (admin)"
echo "   on 200 writes work again; on 503 maintenance is held — do NOT force-clear."
echo "6) rollback evidence (injected failure only): commit answers 503 restore_rolled_back,"
echo "   live rows byte-identical, operator log carries outcome rolled_back."
echo
echo "cookie jar: ${COOKIE_JAR} (login first: POST /api/v1/auth/login)"
echo "operator log: \$X_INSIGHT_RECOVERY_LOG or backend/var/recovery-operator.log"
