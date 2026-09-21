# Database Migrations

> 24 nodes · cohesion 0.09

## Key Concepts

- **alembic** (7 connections)
- **env.py** (7 connections) — `backend/migrations/env.py`
- **0003_physicians.py** (5 connections) — `backend/migrations/versions/0003_physicians.py`
- **0005_drafts.py** (5 connections) — `backend/migrations/versions/0005_drafts.py`
- **0001_init.py** (4 connections) — `backend/migrations/versions/0001_init.py`
- **0002_identity.py** (4 connections) — `backend/migrations/versions/0002_identity.py`
- **0004_patients.py** (4 connections) — `backend/migrations/versions/0004_patients.py`
- **_database_url()** (3 connections) — `backend/migrations/env.py`
- **run_migrations_offline()** (3 connections) — `backend/migrations/env.py`
- **run_migrations_online()** (3 connections) — `backend/migrations/env.py`
- **sqlalchemy_dialects_postgresql** (2 connections)
- **Run migrations in 'offline' mode. This configures the context with just a URL…** (1 connections) — `backend/migrations/env.py`
- **Run migrations in 'online' mode. In this scenario we need to create an Engine…** (1 connections) — `backend/migrations/env.py`
- **downgrade()** (1 connections) — `backend/migrations/versions/0001_init.py`
- **upgrade()** (1 connections) — `backend/migrations/versions/0001_init.py`
- **downgrade()** (1 connections) — `backend/migrations/versions/0002_identity.py`
- **upgrade()** (1 connections) — `backend/migrations/versions/0002_identity.py`
- **downgrade()** (1 connections) — `backend/migrations/versions/0003_physicians.py`
- **upgrade()** (1 connections) — `backend/migrations/versions/0003_physicians.py`
- **downgrade()** (1 connections) — `backend/migrations/versions/0004_patients.py`
- **upgrade()** (1 connections) — `backend/migrations/versions/0004_patients.py`
- **downgrade()** (1 connections) — `backend/migrations/versions/0005_drafts.py`
- **upgrade()** (1 connections) — `backend/migrations/versions/0005_drafts.py`
- **logging_config** (1 connections)

## Relationships

- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (6 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (1 shared connections)
- [Database Engine and Readiness](Database_Engine_and_Readiness.md) (1 shared connections)

## Source Files

- `backend/migrations/env.py`
- `backend/migrations/versions/0001_init.py`
- `backend/migrations/versions/0002_identity.py`
- `backend/migrations/versions/0003_physicians.py`
- `backend/migrations/versions/0004_patients.py`
- `backend/migrations/versions/0005_drafts.py`

## Audit Trail

- EXTRACTED: 34 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*