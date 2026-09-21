# .__call__

> 8 nodes

## Key Concepts

- **.__call__()** (5 connections) — `backend/src/x_insight/app.py`
- **new_request_id()** (5 connections) — `backend/src/x_insight/contracts.py`
- **RequestContextMiddleware** (4 connections) — `backend/src/x_insight/app.py`
- **Any** (3 connections)
- **.__init__()** (2 connections) — `backend/src/x_insight/app.py`
- **send_with_id()** (1 connections) — `backend/src/x_insight/app.py`
- **Propagate/generate request IDs, enforce body size, echo ID on errors.** (1 connections) — `backend/src/x_insight/app.py`
- **Return a new random request correlation ID (UUID text).** (1 connections) — `backend/src/x_insight/contracts.py`

## Relationships

- [app.py](app.py.md) (4 shared connections)
- [routes.py](routes.py.md) (1 shared connections)
- [encounters.py](encounters.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/app.py`
- `backend/src/x_insight/contracts.py`

## Audit Trail

- EXTRACTED: 13 (93%)
- INFERRED: 1 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*