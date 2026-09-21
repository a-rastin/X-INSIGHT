# Request ID Middleware

> 8 nodes · cohesion 0.29

## Key Concepts

- **.__call__()** (5 connections) — `backend/src/x_insight/app.py`
- **new_request_id()** (5 connections) — `backend/src/x_insight/contracts.py`
- **RequestContextMiddleware** (4 connections) — `backend/src/x_insight/app.py`
- **Any** (3 connections)
- **.__init__()** (2 connections) — `backend/src/x_insight/app.py`
- **Propagate/generate request IDs, enforce body size, echo ID on errors.** (1 connections) — `backend/src/x_insight/app.py`
- **send_with_id()** (1 connections) — `backend/src/x_insight/app.py`
- **Return a new random request correlation ID (UUID text).** (1 connections) — `backend/src/x_insight/contracts.py`

## Relationships

- [App Middleware and Errors](App_Middleware_and_Errors.md) (5 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/app.py`
- `backend/src/x_insight/contracts.py`

## Audit Trail

- EXTRACTED: 13 (93%)
- INFERRED: 1 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*