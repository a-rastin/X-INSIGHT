# Health Endpoint

> 3 nodes · cohesion 0.67

## Key Concepts

- **health()** (3 connections) — `backend/src/x_insight/app.py`
- **get** (2 connections)
- **Liveness only; never touches the database.** (1 connections) — `backend/src/x_insight/app.py`

## Relationships

- [App Middleware and Errors](App_Middleware_and_Errors.md) (2 shared connections)

## Source Files

- `backend/src/x_insight/app.py`

## Audit Trail

- EXTRACTED: 4 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*