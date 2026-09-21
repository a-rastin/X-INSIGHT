# conftest.py

> 33 nodes

## Key Concepts

- **conftest.py** (9 connections) — `backend/tests/conftest.py`
- **env.py** (7 connections) — `backend/migrations/env.py`
- **alembic** (7 connections)
- **0003_physicians.py** (5 connections) — `backend/migrations/versions/0003_physicians.py`
- **0005_drafts.py** (5 connections) — `backend/migrations/versions/0005_drafts.py`
- **pytest** (5 connections)
- **0001_init.py** (4 connections) — `backend/migrations/versions/0001_init.py`
- **0002_identity.py** (4 connections) — `backend/migrations/versions/0002_identity.py`
- **0004_patients.py** (4 connections) — `backend/migrations/versions/0004_patients.py`
- **_database_url()** (3 connections) — `backend/migrations/env.py`
- **run_migrations_offline()** (3 connections) — `backend/migrations/env.py`
- **run_migrations_online()** (3 connections) — `backend/migrations/env.py`
- **_migrated_test_db()** (3 connections) — `backend/tests/conftest.py`
- **os** (3 connections)
- **_isolate_audit_rows()** (2 connections) — `backend/tests/conftest.py`
- **_upgrade_test_db()** (2 connections) — `backend/tests/conftest.py`
- **fixture** (2 connections)
- **sqlalchemy_dialects_postgresql** (2 connections)
- **downgrade()** (1 connections) — `backend/migrations/versions/0001_init.py`
- **upgrade()** (1 connections) — `backend/migrations/versions/0001_init.py`
- **downgrade()** (1 connections) — `backend/migrations/versions/0002_identity.py`
- **upgrade()** (1 connections) — `backend/migrations/versions/0002_identity.py`
- **downgrade()** (1 connections) — `backend/migrations/versions/0003_physicians.py`
- **upgrade()** (1 connections) — `backend/migrations/versions/0003_physicians.py`
- **downgrade()** (1 connections) — `backend/migrations/versions/0004_patients.py`
- *... and 8 more nodes in this community*

## Relationships

- [patients.py](patients.py.md) (8 shared connections)
- [test_drafts.py](test_drafts.py.md) (3 shared connections)
- [test_identity.py](test_identity.py.md) (1 shared connections)

## Source Files

- `backend/migrations/env.py`
- `backend/migrations/versions/0001_init.py`
- `backend/migrations/versions/0002_identity.py`
- `backend/migrations/versions/0003_physicians.py`
- `backend/migrations/versions/0004_patients.py`
- `backend/migrations/versions/0005_drafts.py`
- `backend/tests/conftest.py`

## Audit Trail

- EXTRACTED: 50 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*