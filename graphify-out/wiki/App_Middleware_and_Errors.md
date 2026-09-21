# App Middleware and Errors

> 20 nodes · cohesion 0.18

## Key Concepts

- **app.py** (36 connections) — `backend/src/x_insight/app.py`
- **error_body()** (15 connections) — `backend/src/x_insight/contracts.py`
- **ready()** (9 connections) — `backend/src/x_insight/app.py`
- **_http_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_unhandled_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_validation_exception_handler()** (8 connections) — `backend/src/x_insight/app.py`
- **_request_id()** (7 connections) — `backend/src/x_insight/app.py`
- **Request** (5 connections)
- **JSONResponse** (3 connections)
- **exception_handler** (3 connections)
- **Exception** (1 connections)
- **Standard envelope for HTTP errors (shared with handler registration).** (1 connections) — `backend/src/x_insight/app.py`
- **Standard 422 envelope with field errors.** (1 connections) — `backend/src/x_insight/app.py`
- **Safe 500 envelope: no traceback, no secrets.** (1 connections) — `backend/src/x_insight/app.py`
- **Readiness: database reachable and schema at the expected revision.** (1 connections) — `backend/src/x_insight/app.py`
- **Build the standard error envelope (plan section 4.3).** (1 connections) — `backend/src/x_insight/contracts.py`
- **fastapi_exceptions** (1 connections)
- **RequestValidationError** (1 connections)
- **starlette_exceptions** (1 connections)
- **StarletteHTTPException** (1 connections)

## Relationships

- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (7 shared connections)
- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (7 shared connections)
- [Request ID Middleware](Request_ID_Middleware.md) (5 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (3 shared connections)
- [Released Content Tests](Released_Content_Tests.md) (2 shared connections)
- [Database Engine and Readiness](Database_Engine_and_Readiness.md) (2 shared connections)
- [Health Endpoint](Health_Endpoint.md) (2 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (1 shared connections)
- [Patient Registration](Patient_Registration.md) (1 shared connections)
- [Physician Accounts and Transactions](Physician_Accounts_and_Transactions.md) (1 shared connections)
- [HTTP Contract Tests](HTTP_Contract_Tests.md) (1 shared connections)
- [C-SSRS HTTP Tests](C-SSRS_HTTP_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/app.py`
- `backend/src/x_insight/contracts.py`

## Audit Trail

- EXTRACTED: 76 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*