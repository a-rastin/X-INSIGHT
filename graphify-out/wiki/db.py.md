# db.py

> 16 nodes

## Key Concepts

- **db.py** (17 connections) — `backend/src/x_insight/db.py`
- **get_engine()** (7 connections) — `backend/src/x_insight/db.py`
- **check_readiness()** (6 connections) — `backend/src/x_insight/db.py`
- **ReadinessError** (5 connections) — `backend/src/x_insight/db.py`
- **database_url_for()** (4 connections) — `backend/src/x_insight/db.py`
- **.__init__()** (3 connections) — `backend/src/x_insight/db.py`
- **dispose_engines()** (2 connections) — `backend/src/x_insight/db.py`
- **_sqlalchemy_url()** (2 connections) — `backend/src/x_insight/db.py`
- **Exception** (1 connections)
- **Engine** (1 connections)
- **PostgreSQL connection lifecycle and readiness. Roles are logical connection…** (1 connections) — `backend/src/x_insight/db.py`
- **Database readiness failure with a public code.** (1 connections) — `backend/src/x_insight/db.py`
- **Return the configured URL for a logical role.** (1 connections) — `backend/src/x_insight/db.py`
- **Return a cached engine for the given URL (or the app role).** (1 connections) — `backend/src/x_insight/db.py`
- **Dispose cached engines (tests, process restart).** (1 connections) — `backend/src/x_insight/db.py`
- **Raise ReadinessError(UNAVAILABLE|INCOMPATIBLE_SCHEMA) when not ready.** (1 connections) — `backend/src/x_insight/db.py`

## Relationships

- [accounts.py](accounts.py.md) (3 shared connections)
- [contracts.py](contracts.py.md) (3 shared connections)
- [app.py](app.py.md) (2 shared connections)
- [conftest.py](conftest.py.md) (1 shared connections)
- [connections.py](connections.py.md) (1 shared connections)
- [patients.py](patients.py.md) (1 shared connections)
- [routes.py](routes.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/db.py`

## Audit Trail

- EXTRACTED: 33 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*