# HTTP Contract Tests

> 12 nodes · cohesion 0.27

## Key Concepts

- **test_contracts.py** (12 connections) — `backend/tests/http/test_contracts.py`
- **_client()** (9 connections) — `backend/tests/http/test_contracts.py`
- **test_validation_errors_use_standard_envelope()** (3 connections) — `backend/tests/http/test_contracts.py`
- **test_client_request_id_is_propagated()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_health_does_not_require_database()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_oversized_body_returns_413_envelope()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_ready_reports_incompatible_when_schema_missing()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_ready_reports_ready_when_database_migrated()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_ready_reports_unavailable_when_database_unreachable()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_unknown_route_returns_standard_envelope_with_correlation()** (2 connections) — `backend/tests/http/test_contracts.py`
- **TestClient** (1 connections)
- **create()** (1 connections) — `backend/tests/http/test_contracts.py`

## Relationships

- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (2 shared connections)
- [HTTP Tests and Fixtures](HTTP_Tests_and_Fixtures.md) (1 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_contracts.py`

## Audit Trail

- EXTRACTED: 22 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*