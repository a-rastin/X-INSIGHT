# health

> 3 nodes

## Key Concepts

- **health()** (3 connections) — `backend/src/x_insight/app.py`
- **get** (2 connections)
- **Liveness only; never touches the database.** (1 connections) — `backend/src/x_insight/app.py`

## Relationships

- [app.py](app.py.md) (2 shared connections)

## Source Files

- `backend/src/x_insight/app.py`

## Audit Trail

- EXTRACTED: 4 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*