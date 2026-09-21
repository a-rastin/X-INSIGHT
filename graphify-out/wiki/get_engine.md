# get_engine

> 8 nodes

## Key Concepts

- **get_engine()** (7 connections) — `backend/src/x_insight/db.py`
- **check_readiness()** (6 connections) — `backend/src/x_insight/db.py`
- **database_url_for()** (4 connections) — `backend/src/x_insight/db.py`
- **_sqlalchemy_url()** (2 connections) — `backend/src/x_insight/db.py`
- **Engine** (1 connections)
- **Return the configured URL for a logical role.** (1 connections) — `backend/src/x_insight/db.py`
- **Return a cached engine for the given URL (or the app role).** (1 connections) — `backend/src/x_insight/db.py`
- **Raise ReadinessError(UNAVAILABLE|INCOMPATIBLE_SCHEMA) when not ready.** (1 connections) — `backend/src/x_insight/db.py`

## Relationships

- [patients.py](patients.py.md) (4 shared connections)
- [ready](ready.md) (1 shared connections)
- [ReadinessError](ReadinessError.md) (1 shared connections)
- [transaction](transaction.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/db.py`

## Audit Trail

- EXTRACTED: 15 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*