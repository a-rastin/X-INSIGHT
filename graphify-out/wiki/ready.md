# ready

> 26 nodes

## Key Concepts

- **ready()** (9 connections) — `backend/src/x_insight/app.py`
- **_http_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_unhandled_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_validation_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_request_id()** (7 connections) — `backend/src/x_insight/app.py`
- **.__call__()** (5 connections) — `backend/src/x_insight/app.py`
- **new_request_id()** (5 connections) — `backend/src/x_insight/contracts.py`
- **Request** (5 connections)
- **RequestContextMiddleware** (4 connections) — `backend/src/x_insight/app.py`
- **health()** (3 connections) — `backend/src/x_insight/app.py`
- **Any** (3 connections)
- **JSONResponse** (3 connections)
- **exception_handler** (3 connections)
- **.__init__()** (2 connections) — `backend/src/x_insight/app.py`
- **get** (2 connections)
- **send_with_id()** (1 connections) — `backend/src/x_insight/app.py`
- **Exception** (1 connections)
- **RequestValidationError** (1 connections)
- **StarletteHTTPException** (1 connections)
- **Standard envelope for HTTP errors (shared with handler registration).** (1 connections) — `backend/src/x_insight/app.py`
- **Standard 422 envelope with field errors.** (1 connections) — `backend/src/x_insight/app.py`
- **Safe 500 envelope: no traceback, no secrets.** (1 connections) — `backend/src/x_insight/app.py`
- **Liveness only; never touches the database.** (1 connections) — `backend/src/x_insight/app.py`
- **Readiness: database reachable and schema at the expected revision.** (1 connections) — `backend/src/x_insight/app.py`
- **Propagate/generate request IDs, enforce body size, echo ID on errors.** (1 connections) — `backend/src/x_insight/app.py`
- *... and 1 more nodes in this community*

## Relationships

- [routes.py](routes.py.md) (9 shared connections)
- [_require_session](_require_session.md) (5 shared connections)
- [get_engine](get_engine.md) (1 shared connections)
- [Project Knowledge Base](Project_Knowledge_Base.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/app.py`
- `backend/src/x_insight/contracts.py`

## Audit Trail

- EXTRACTED: 49 (96%)
- INFERRED: 2 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*