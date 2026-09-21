# Released Content Tests

> 12 nodes · cohesion 0.21

## Key Concepts

- **test_content.py** (14 connections) — `backend/tests/http/test_content.py`
- **fastapi_testclient** (11 connections)
- **login()** (4 connections) — `backend/tests/http/test_content.py`
- **clean_content()** (3 connections) — `backend/tests/http/test_content.py`
- **test_health.py** (3 connections) — `backend/tests/http/test_health.py`
- **test_draft_definitions_not_exposed()** (2 connections) — `backend/tests/http/test_content.py`
- **test_released_definition_served_from_content_dir()** (2 connections) — `backend/tests/http/test_content.py`
- **test_unknown_assessment_type_not_found()** (2 connections) — `backend/tests/http/test_content.py`
- **fixture** (1 connections)
- **Slice 4 (RED): authenticated released-only content routes (T1, real PG). No…** (1 connections) — `backend/tests/http/test_content.py`
- **test_anonymous_content_denied()** (1 connections) — `backend/tests/http/test_content.py`
- **test_process_reports_liveness()** (1 connections) — `backend/tests/http/test_health.py`

## Relationships

- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (2 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (2 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (2 shared connections)
- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (1 shared connections)
- [Login Throttle and Clock](Login_Throttle_and_Clock.md) (1 shared connections)
- [Test Fixture Resets](Test_Fixture_Resets.md) (1 shared connections)
- [HTTP Contract Tests](HTTP_Contract_Tests.md) (1 shared connections)
- [C-SSRS HTTP Tests](C-SSRS_HTTP_Tests.md) (1 shared connections)
- [Diagnosis Evaluation Tests](Diagnosis_Evaluation_Tests.md) (1 shared connections)
- [Draft Lifecycle Tests](Draft_Lifecycle_Tests.md) (1 shared connections)
- [History HTTP Tests](History_HTTP_Tests.md) (1 shared connections)
- [PANSS Evaluation Tests](PANSS_Evaluation_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_content.py`
- `backend/tests/http/test_health.py`

## Audit Trail

- EXTRACTED: 31 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*