# HTTP Contract Tests

> 10 nodes · cohesion 0.36

## Key Concepts

- **test_contracts.py** (12 connections) — `backend/tests/http/test_contracts.py`
- **_client()** (9 connections) — `backend/tests/http/test_contracts.py`
- **test_client_request_id_is_propagated()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_health_does_not_require_database()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_oversized_body_returns_413_envelope()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_ready_reports_incompatible_when_schema_missing()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_ready_reports_ready_when_database_migrated()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_ready_reports_unavailable_when_database_unreachable()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_unknown_route_returns_standard_envelope_with_correlation()** (2 connections) — `backend/tests/http/test_contracts.py`
- **TestClient** (1 connections)

## Relationships

- [Released Content Tests](Released_Content_Tests.md) (1 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (1 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (1 shared connections)
- [App Exception Handlers](App_Exception_Handlers.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_contracts.py`

## Audit Trail

- EXTRACTED: 20 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*