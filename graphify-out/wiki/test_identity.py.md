# test_identity.py

> 56 nodes

## Key Concepts

- **test_identity.py** (30 connections) — `backend/tests/http/test_identity.py`
- **_client()** (17 connections) — `backend/tests/http/test_identity.py`
- **_login()** (16 connections) — `backend/tests/http/test_identity.py`
- **conftest.py** (9 connections) — `backend/tests/conftest.py`
- **pytest** (8 connections)
- **env.py** (7 connections) — `backend/migrations/env.py`
- **alembic** (7 connections)
- **test_second_initialization_preserves_changed_password()** (5 connections) — `backend/tests/http/test_identity.py`
- **0003_physicians.py** (5 connections) — `backend/migrations/versions/0003_physicians.py`
- **0005_drafts.py** (5 connections) — `backend/migrations/versions/0005_drafts.py`
- **test_audit_records_success_and_failure_without_credentials()** (4 connections) — `backend/tests/http/test_identity.py`
- **test_empty_password_fails_without_trimming()** (4 connections) — `backend/tests/http/test_identity.py`
- **test_inactive_account_cannot_login()** (4 connections) — `backend/tests/http/test_identity.py`
- **0001_init.py** (4 connections) — `backend/migrations/versions/0001_init.py`
- **0002_identity.py** (4 connections) — `backend/migrations/versions/0002_identity.py`
- **0004_patients.py** (4 connections) — `backend/migrations/versions/0004_patients.py`
- **_database_url()** (3 connections) — `backend/migrations/env.py`
- **run_migrations_offline()** (3 connections) — `backend/migrations/env.py`
- **run_migrations_online()** (3 connections) — `backend/migrations/env.py`
- **_migrated_test_db()** (3 connections) — `backend/tests/conftest.py`
- **test_admin_username_mutation_is_denied()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_fresh_database_permits_admin_admin()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_login_sets_opaque_cookie_and_me()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_login_throttling_returns_429()** (3 connections) — `backend/tests/http/test_identity.py`
- **test_logout_revokes_current_session()** (3 connections) — `backend/tests/http/test_identity.py`
- *... and 31 more nodes in this community*

## Relationships

- [encounters.py](encounters.py.md) (10 shared connections)
- [routes.py](routes.py.md) (5 shared connections)
- [store.py](store.py.md) (3 shared connections)
- [test_content.py](test_content.py.md) (2 shared connections)
- [app.py](app.py.md) (1 shared connections)
- [reset_all](reset_all.md) (1 shared connections)
- [test_definitions.py](test_definitions.py.md) (1 shared connections)
- [http/test_diagnosis.py](http-test_diagnosis.py.md) (1 shared connections)
- [physician](physician.md) (1 shared connections)
- [test_patients.py](test_patients.py.md) (1 shared connections)
- [test_physicians.py](test_physicians.py.md) (1 shared connections)
- [patients.py](patients.py.md) (1 shared connections)

## Source Files

- `backend/migrations/env.py`
- `backend/migrations/versions/0001_init.py`
- `backend/migrations/versions/0002_identity.py`
- `backend/migrations/versions/0003_physicians.py`
- `backend/migrations/versions/0004_patients.py`
- `backend/migrations/versions/0005_drafts.py`
- `backend/tests/conftest.py`
- `backend/tests/http/test_identity.py`

## Audit Trail

- EXTRACTED: 121 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*