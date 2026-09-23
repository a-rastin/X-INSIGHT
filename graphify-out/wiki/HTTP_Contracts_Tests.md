# HTTP Contracts Tests

> 15 nodes · cohesion 0.20

## Key Concepts

- **fastapi_testclient** (22 connections)
- **test_contracts.py** (12 connections) — `backend/tests/http/test_contracts.py`
- **_client()** (9 connections) — `backend/tests/http/test_contracts.py`
- **test_validation_errors_use_standard_envelope()** (3 connections) — `backend/tests/http/test_contracts.py`
- **test_health.py** (3 connections) — `backend/tests/http/test_health.py`
- **test_client_request_id_is_propagated()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_health_does_not_require_database()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_oversized_body_returns_413_envelope()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_ready_reports_incompatible_when_schema_missing()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_ready_reports_ready_when_database_migrated()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_ready_reports_unavailable_when_database_unreachable()** (2 connections) — `backend/tests/http/test_contracts.py`
- **test_unknown_route_returns_standard_envelope_with_correlation()** (2 connections) — `backend/tests/http/test_contracts.py`
- **TestClient** (1 connections)
- **create()** (1 connections) — `backend/tests/http/test_contracts.py`
- **test_process_reports_liveness()** (1 connections) — `backend/tests/http/test_health.py`

## Relationships

- [Knowledge Base App](Knowledge_Base_App.md) (3 shared connections)
- [Worker Single Question Tests](Worker_Single_Question_Tests.md) (2 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [HTTP Content Tests](HTTP_Content_Tests.md) (1 shared connections)
- [HTTP C-SSRS Tests](HTTP_C-SSRS_Tests.md) (1 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (1 shared connections)
- [HTTP Diagnosis Tests](HTTP_Diagnosis_Tests.md) (1 shared connections)
- [HTTP Drafts Tests](HTTP_Drafts_Tests.md) (1 shared connections)
- [HTTP Followup Tests](HTTP_Followup_Tests.md) (1 shared connections)
- [MCP Server](MCP_Server.md) (1 shared connections)
- [HTTP Identity Tests](HTTP_Identity_Tests.md) (1 shared connections)
- [HTTP Medications Tests](HTTP_Medications_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_contracts.py`
- `backend/tests/http/test_health.py`

## Audit Trail

- EXTRACTED: 45 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*