# get_engine

> 12 nodes

## Key Concepts

- **get_engine()** (7 connections) — `backend/src/x_insight/db.py`
- **check_readiness()** (6 connections) — `backend/src/x_insight/db.py`
- **ReadinessError** (5 connections) — `backend/src/x_insight/db.py`
- **database_url_for()** (4 connections) — `backend/src/x_insight/db.py`
- **.__init__()** (3 connections) — `backend/src/x_insight/db.py`
- **_sqlalchemy_url()** (2 connections) — `backend/src/x_insight/db.py`
- **Exception** (1 connections)
- **Engine** (1 connections)
- **Database readiness failure with a public code.** (1 connections) — `backend/src/x_insight/db.py`
- **Return the configured URL for a logical role.** (1 connections) — `backend/src/x_insight/db.py`
- **Return a cached engine for the given URL (or the app role).** (1 connections) — `backend/src/x_insight/db.py`
- **Raise ReadinessError(UNAVAILABLE|INCOMPATIBLE_SCHEMA) when not ready.** (1 connections) — `backend/src/x_insight/db.py`

## Relationships

- [routes.py](routes.py.md) (5 shared connections)
- [ready](ready.md) (1 shared connections)
- [accounts.py](accounts.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/db.py`

## Audit Trail

- EXTRACTED: 20 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*