# X-INSIGHT restore operator recovery procedure (S56)

Disposable-drill only. Never run against the owner's live database.

## Preconditions

- Admin credentials for the disposable deployment; network access to the
  application origin only (`/api/v1`; database and MCP have no public ports).
- A backup archive produced by `POST /api/v1/backups` from the same
  application major/schema line (`db_schema_revision` must match live).

## Protocol (explicit phases — not one SQL transaction)

1. **Backup.** `POST /api/v1/backups` (admin, `Idempotency-Key`) → `202`.
   Poll `GET /api/v1/backups/{id}` to `succeeded`; download the zip.
2. **Stage.** `POST /api/v1/restores/validate` (multipart field `archive`).
   Inspect `GET /api/v1/restores/{id}`: backup id/timestamp, schema/content
   checksums, live-vs-staged impact, key-reentry note, immutable
   `confirmation_digest`, `expired`/`superseded` flags. Live state is
   untouched (reads through public HTTP are byte-identical).
3. **Commit (exact digest only).** `POST /api/v1/restores/commit`
   `{restore_id, confirmation_digest}` (admin, `Idempotency-Key`).
   A stale/superseded/expired/mismatched digest fails (`409`/`422`) with no
   live mutation. On success the application: enters file-based maintenance
   (`$X_INSIGHT_MAINTENANCE_FILE` or `backend/var/maintenance.json`,
   independent of either database), fences `deployment_state.generation`
   (`+1`, so old provider work cannot commit), takes a pre-restore backup
   job (`pre_restore_backup_id`), replaces domain tables in phases from the
   staged `database/*.json` (users keep live password hashes; staged-only
   ids get an unusable placeholder; `recovery_jobs`/`alembic_version` never
   replaced; fenced generation kept), revokes all sessions/grants, cancels
   restored nonterminal runs/jobs for explicit restart, records
   `restore.commit` in the restored audit and appends `outcome: committed`
   to the external operator log
   (`$X_INSIGHT_RECOVERY_LOG` or `backend/var/recovery-operator.log`).
4. **Verify while fenced.** Fresh admin login works (old sessions are
   revoked); `GET /patients` reads staged data; `GET /restores/{id}` shows
   `committed`; mutating writes answer `503 MAINTENANCE`; queued worker
   claims return nothing.
5. **Reopen only on health.** `POST /api/v1/restores/{id}/reopen` (admin).
   The application checks readiness (schema revision, generation, patient
   readability, committed marker). `200 reopened` clears maintenance and
   writes work again. `503` keeps maintenance — investigate, do not
   force-clear the flag file.

## Rollback

- Failure **before switch** or **during restart** (including injected
  `X_INSIGHT_RESTORE_FAIL_BEFORE_SWITCH` /
  `X_INSIGHT_RESTORE_FAIL_DURING_RESTART`): the application re-applies the
  pre-restore backup snapshot, restores the pre-commit generation, keeps
  maintenance active, leaves the restore row `staged` with
  `commit_error: restore_rolled_back`, and appends
  `outcome: rolled_back` to the operator log. The commit answers `503`.
  Live records remain readable; reopen stays `503` until a later healthy
  commit.
- Failure **at health** (`X_INSIGHT_RESTORE_FAIL_AT_HEALTH` or a real
  unhealthy check): replaced tables stay; reopen answers `503` with the
  fence held. Clear the cause, then reopen (`200`) — no auto-rollback.

## Notes

- Replacement, never merge: extra live rows not in the archive disappear.
- Sessions are excluded from portable archives and revoked on every commit;
  all users log in again. Provider ciphertext restores, but without the
  original `X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY` affected revisions stay
  unreadable until key re-entry (see staging report note).
- `deploy/maintenance.sh status` inspects the flag file plus `/ready`;
  `deploy/restore-switch.sh` prints this drill sequence.
