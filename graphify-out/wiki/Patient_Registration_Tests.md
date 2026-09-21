# Patient Registration Tests

> 13 nodes · cohesion 0.26

## Key Concepts

- **test_patients.py** (14 connections) — `backend/tests/http/test_patients.py`
- **test_concurrent_duplicate_archived_and_idempotent_create()** (6 connections) — `backend/tests/http/test_patients.py`
- **headers()** (5 connections) — `backend/tests/http/test_patients.py`
- **login()** (5 connections) — `backend/tests/http/test_patients.py`
- **test_patient_field_validation_rejects_bad_demographics()** (5 connections) — `backend/tests/http/test_patients.py`
- **test_physician_registers_patient_with_registration_draft()** (5 connections) — `backend/tests/http/test_patients.py`
- **test_directory_search_filter_pagination_shared()** (4 connections) — `backend/tests/http/test_patients.py`
- **S06 slice 1: physician patient registration + registration draft (T1, real PG).** (1 connections) — `backend/tests/http/test_patients.py`
- **Slice 3: exactly-one concurrent create; archived IDs still conflict; idempotent…** (1 connections) — `backend/tests/http/test_patients.py`
- **Slice 4 (T1): shared directory search with filters + cursor pagination.…** (1 connections) — `backend/tests/http/test_patients.py`
- **Response shape: {"schema_version":1,"patient":{...,"patient_id":"0012345678",…** (1 connections) — `backend/tests/http/test_patients.py`
- **Slice 2: 422 + field_errors for bad demographics; NFC name succeeds.** (1 connections) — `backend/tests/http/test_patients.py`
- **attempt()** (1 connections) — `backend/tests/http/test_patients.py`

## Relationships

- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (3 shared connections)
- [History HTTP Tests](History_HTTP_Tests.md) (3 shared connections)
- [HTTP Tests and Fixtures](HTTP_Tests_and_Fixtures.md) (2 shared connections)
- [Login Throttle and Clock](Login_Throttle_and_Clock.md) (1 shared connections)
- [Test Fixture Resets](Test_Fixture_Resets.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_patients.py`

## Audit Trail

- EXTRACTED: 26 (87%)
- INFERRED: 4 (13%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*