# ready

> 15 nodes

## Key Concepts

- **ready()** (9 connections) — `backend/src/x_insight/app.py`
- **_http_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_unhandled_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_validation_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_request_id()** (7 connections) — `backend/src/x_insight/app.py`
- **Request** (5 connections)
- **JSONResponse** (3 connections)
- **exception_handler** (3 connections)
- **Exception** (1 connections)
- **RequestValidationError** (1 connections)
- **StarletteHTTPException** (1 connections)
- **Standard envelope for HTTP errors (shared with handler registration).** (1 connections) — `backend/src/x_insight/app.py`
- **Standard 422 envelope with field errors.** (1 connections) — `backend/src/x_insight/app.py`
- **Safe 500 envelope: no traceback, no secrets.** (1 connections) — `backend/src/x_insight/app.py`
- **Readiness: database reachable and schema at the expected revision.** (1 connections) — `backend/src/x_insight/app.py`

## Relationships

- [patients.py](patients.py.md) (6 shared connections)
- [routes.py](routes.py.md) (4 shared connections)
- [get_engine](get_engine.md) (1 shared connections)
- [health](health.md) (1 shared connections)
- [Any](Any.md) (1 shared connections)
- [Project Knowledge Base](Project_Knowledge_Base.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/app.py`

## Audit Trail

- EXTRACTED: 35 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*