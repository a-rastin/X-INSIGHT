# App Exception Handlers

> 4 nodes · cohesion 0.50

## Key Concepts

- **register_exception_handlers()** (4 connections) — `backend/src/x_insight/app.py`
- **test_validation_errors_use_standard_envelope()** (3 connections) — `backend/tests/http/test_contracts.py`
- **Attach the standard contract handlers to another app (tests reuse).** (1 connections) — `backend/src/x_insight/app.py`
- **create()** (1 connections) — `backend/tests/http/test_contracts.py`

## Relationships

- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (1 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (1 shared connections)
- [HTTP Contract Tests](HTTP_Contract_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/app.py`
- `backend/tests/http/test_contracts.py`

## Audit Trail

- EXTRACTED: 6 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*