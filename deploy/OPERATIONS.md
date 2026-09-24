# X-INSIGHT production operations (S57)

Localhost/disposable target only. Never run these procedures against the
owner's live database, and never point them at an external host: all
commands and scripts below default to `http://localhost:8000` and the local
`deploy/compose.prod.yaml` stack. Fresh install uses `deploy/setup.sh`;
upgrades use `deploy/upgrade.sh`; restore drills use
`deploy/restore-switch.sh` (see `docs/dev/recovery-runbook.md`).

## Environment variables

Production configuration comes from the deployment environment, never from
checked-in values:

- `DB_PASSWORD` (required): database credential. Referenced in
  `deploy/compose.prod.yaml` as `${DB_PASSWORD:?set DB_PASSWORD}` for
  `DATABASE_URL` (app/worker) and `POSTGRES_PASSWORD` (db). No default.
- `X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY` (required): operator-held
  provider-key encryption key (Fernet key text, or a passphrase the
  application derives via SHA-256; see
  `backend/src/x_insight/reasoning/provider_config.py`
  `ENCRYPTION_ENV_VARS`). Referenced in `deploy/compose.prod.yaml` as
  `${X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY:?set X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY}`
  on app and worker. No default, no checked-in value.
- `X_INSIGHT_PROVIDER_ALLOW_LOCAL` must NOT be set in production. It is the
  dev-only local-endpoint flag; setting it would permit loopback provider
  endpoints.
- Operator-script conveniences (defaults are localhost-safe):
  `X_INSIGHT_BASE_URL` (default `http://localhost:8000`),
  `X_INSIGHT_MAINTENANCE_FILE` (default `backend/var/maintenance.json`),
  `X_INSIGHT_RECOVERY_LOG` (default `backend/var/recovery-operator.log`).

Placeholder values only live in `deploy/.env.prod.example`; real secrets go
in the untracked deployment environment. `.env.example` stays
placeholders-only for local development.

## Secret and key handling

- The provider encryption key is held outside the database (process
  environment on app/worker only). It is never stored in a table column;
  only Fernet ciphertext is stored.
- The key is never included in backup archives. Portable archives exclude
  the `sessions` table and the deployment encryption key
  (`excludes: ["sessions", "deployment_encryption_key"]` in
  `backend/src/x_insight/operations/backup.py`); the manifest carries a
  key-reentry note instead.
- Key re-entry after restore: provider ciphertext restores, but without the
  original `X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY` the affected revisions
  stay unreadable until the original key is re-entered in the environment.
  Decryption failure raises (stored key cannot be decrypted); re-enter the
  key, do not edit the ciphertext.
- If the variable is unset the application logs a dev-only deterministic
  fallback warning. Do not rely on the fallback in production; always set
  the required variable before starting app/worker.

## Backup before upgrade

Every upgrade starts with a successful backup; `deploy/upgrade.sh` step 1
does this and aborts if the backup fails:

1. `POST /api/v1/backups` (admin session cookie, `Idempotency-Key` header,
   JSON body `{}`) answers `202` with `{"job_id": ..., "status": ...}`.
2. Poll `GET /api/v1/backups/{job_id}` (admin) until `status` is
   `succeeded` (`failed` aborts the upgrade).
3. Optionally `GET /api/v1/backups/{job_id}/download` saves the zip for
   the rollback window.

Do not skip this step. The pre-restore backup taken automatically on
`POST /api/v1/restores/commit` is a second safety net, not a replacement
for the pre-upgrade backup.

## Compatible application and schema rollback

Releases are image + migration-revision pairs: pinned images in
`deploy/compose.prod.yaml` (exact tags, never `:latest`) plus the alembic
revision applied by `alembic upgrade head`.

- Rollback means redeploying the prior image tags together with the
  matching schema downgrade (`alembic downgrade <prior-revision>`), then
  restarting app/worker/edge. Never mix new code with an old schema or old
  code with a new schema beyond the tested pair.
- Started runs keep the bundle/model revision they were created with;
  rolling back the deployment does not rewrite signed history or audit
  events. Restored nonterminal runs/jobs stay cancelled until explicitly
  restarted (see `docs/dev/recovery-runbook.md`).
- Keep the pre-upgrade backup zip until the new revision is verified
  healthy (`GET /api/v1/ready`, chart reads, admin reads).
- The web bundle is part of the release: `deploy/setup.sh` and
  `deploy/upgrade.sh` rebuild `web/dist`, which edge bind-mounts
  read-only at `/` (`../web/dist:/usr/share/nginx/html:ro` in
  `deploy/compose.prod.yaml`). Rolling back the images without rebuilding
  the bundle leaves a mismatched frontend; rebuild from the prior checkout
  when rolling back.

## Migration-failure recovery

Migrations run as an explicit step (`alembic upgrade head` in
`deploy/setup.sh` and `deploy/upgrade.sh` step 3) under `set -euo
pipefail`: any migration error fails loudly with a nonzero exit.

- `deploy/upgrade.sh` runs the migration BEFORE switching containers. On
  failure it aborts before `compose up -d`, leaves the old app/worker/edge
  containers running, and prints a pointer to this section. The database
  may be part-migrated (alembic transactional DDL per revision); do not
  restart new code on top of it blindly.
- Decide fix-forward vs restore-from-backup:
  - Fix-forward when the failure is understood and the migration is
    re-runnable: fix the cause, rerun `alembic upgrade head`, then rerun
    `deploy/upgrade.sh` step 4.
  - Restore-from-backup when the schema is left in an unclear state or
    fix-forward is not safe: follow `docs/dev/recovery-runbook.md`
    (validate/stage the pre-upgrade backup, commit with the exact digest,
    verify while fenced, reopen only on health).
- Never wipe the `pgdata` volume to "fix" a migration. See the next
  section for what `down -v` would destroy.

## Stopping processes (stop / down)

- `docker compose -f deploy/compose.prod.yaml stop` stops app/worker/edge/db
  containers but keeps them, the network, and the named volume. Start again
  with `up -d`.
- `docker compose -f deploy/compose.prod.yaml down` removes containers and
  the network but preserves the named volume `pgdata`
  (`pgdata:/var/lib/postgresql/data`). Data survives.
- `down -v` would delete `pgdata` and all PostgreSQL data with it. This is
  FORBIDDEN in production and appears in no script here. Never run it, never
  run `docker volume rm` on `pgdata`.
- db publishes no host ports; app is reached only through edge. `setup.sh`
  and `upgrade.sh` never touch volumes.
