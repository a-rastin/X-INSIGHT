# App Middleware and Errors

> 28 nodes · cohesion 0.11

## Key Concepts

- **error_body()** (15 connections) — `backend/src/x_insight/contracts.py`
- **ready()** (9 connections) — `backend/src/x_insight/app.py`
- **_http_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_unhandled_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_validation_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_request_id()** (7 connections) — `backend/src/x_insight/app.py`
- **Request** (5 connections)
- **.__call__()** (5 connections) — `backend/src/x_insight/app.py`
- **new_request_id()** (5 connections) — `backend/src/x_insight/contracts.py`
- **RequestContextMiddleware** (4 connections) — `backend/src/x_insight/app.py`
- **health()** (3 connections) — `backend/src/x_insight/app.py`
- **Any** (3 connections)
- **JSONResponse** (3 connections)
- **exception_handler** (3 connections)
- **get** (2 connections)
- **.__init__()** (2 connections) — `backend/src/x_insight/app.py`
- **Exception** (1 connections)
- **Standard envelope for HTTP errors (shared with handler registration).** (1 connections) — `backend/src/x_insight/app.py`
- **Standard 422 envelope with field errors.** (1 connections) — `backend/src/x_insight/app.py`
- **Safe 500 envelope: no traceback, no secrets.** (1 connections) — `backend/src/x_insight/app.py`
- **Liveness only; never touches the database.** (1 connections) — `backend/src/x_insight/app.py`
- **Readiness: database reachable and schema at the expected revision.** (1 connections) — `backend/src/x_insight/app.py`
- **Propagate/generate request IDs, enforce body size, echo ID on errors.** (1 connections) — `backend/src/x_insight/app.py`
- **send_with_id()** (1 connections) — `backend/src/x_insight/app.py`
- **Return a new random request correlation ID (UUID text).** (1 connections) — `backend/src/x_insight/contracts.py`
- *... and 3 more nodes in this community*

## Relationships

- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (10 shared connections)
- [Patient and Session Routes](Patient_and_Session_Routes.md) (3 shared connections)
- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (3 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (3 shared connections)
- [Knowledge Base Skill](Knowledge_Base_Skill.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/app.py`
- `backend/src/x_insight/contracts.py`

## Audit Trail

- EXTRACTED: 59 (97%)
- INFERRED: 2 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*