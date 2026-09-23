# App Middleware Errors

> 13 nodes · cohesion 0.24

## Key Concepts

- **_request_id()** (18 connections) — `backend/src/x_insight/app.py`
- **_http_exception_handler()** (7 connections) — `backend/src/x_insight/app.py`
- **_unhandled_exception_handler()** (7 connections) — `backend/src/x_insight/app.py`
- **_validation_exception_handler()** (7 connections) — `backend/src/x_insight/app.py`
- **Request** (5 connections)
- **JSONResponse** (3 connections)
- **exception_handler** (3 connections)
- **Exception** (1 connections)
- **Standard envelope for HTTP errors (shared with handler registration).** (1 connections) — `backend/src/x_insight/app.py`
- **Standard 422 envelope with field errors.** (1 connections) — `backend/src/x_insight/app.py`
- **Safe 500 envelope: no traceback, no secrets.** (1 connections) — `backend/src/x_insight/app.py`
- **RequestValidationError** (1 connections)
- **StarletteHTTPException** (1 connections)

## Relationships

- [Knowledge Base App](Knowledge_Base_App.md) (6 shared connections)
- [Cases Encounters](Cases_Encounters.md) (3 shared connections)
- [Models Routes 3](Models_Routes_3.md) (3 shared connections)
- [Reasoning Routes](Reasoning_Routes.md) (3 shared connections)
- [Models Routes 2](Models_Routes_2.md) (2 shared connections)
- [Reasoning Snapshots](Reasoning_Snapshots.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/app.py`

## Audit Trail

- EXTRACTED: 25 (68%)
- INFERRED: 12 (32%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*