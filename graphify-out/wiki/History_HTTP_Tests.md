# History HTTP Tests

> 19 nodes · cohesion 0.27

## Key Concepts

- **physician()** (42 connections) — `backend/src/x_insight/identity/accounts.py`
- **test_history.py** (20 connections) — `backend/tests/http/test_history.py`
- **_login()** (9 connections) — `backend/tests/http/test_history.py`
- **_mutation_headers()** (9 connections) — `backend/tests/http/test_history.py`
- **_encounter()** (7 connections) — `backend/tests/http/test_history.py`
- **test_excluded_medication_regimen_fields_rejected()** (6 connections) — `backend/tests/http/test_history.py`
- **test_history_reconciliation_shape_rejected_when_not_explicit()** (6 connections) — `backend/tests/http/test_history.py`
- **test_undeclared_history_field_rejected_revision_unchanged()** (6 connections) — `backend/tests/http/test_history.py`
- **test_declared_history_values_round_trip_with_server_provenance()** (5 connections) — `backend/tests/http/test_history.py`
- **test_effect_status_and_severity_validation_round_trips_with_provenance()** (5 connections) — `backend/tests/http/test_history.py`
- **test_effect_status_change_requires_explicit_severity_clear()** (5 connections) — `backend/tests/http/test_history.py`
- **test_history_content_route_exposes_released_only()** (5 connections) — `backend/tests/http/test_history.py`
- **test_physician_phone_update_via_patient_patch()** (5 connections) — `backend/tests/http/test_history.py`
- **S12 slice 1 (RED): typed history persistence and provenance (T1). This test…** (1 connections) — `backend/tests/http/test_history.py`
- **S12 slice A: undeclared history field -> 422, revision/draft unchanged.** (1 connections) — `backend/tests/http/test_history.py`
- **S12 slice A (RED): FR-14-excluded regimen fields -> 422, never stored. FR-14…** (1 connections) — `backend/tests/http/test_history.py`
- **S12 slice B (RED): optional phone text update belongs to S12 step 4. Expected…** (1 connections) — `backend/tests/http/test_history.py`
- **S12 slice B (RED): reconciliation state must be validated, not verbatim. S12…** (1 connections) — `backend/tests/http/test_history.py`
- **S12 slice B (RED): GET /content/history serves released versions only. Mirrors…** (1 connections) — `backend/tests/http/test_history.py`

## Relationships

- [Draft Lifecycle Tests](Draft_Lifecycle_Tests.md) (9 shared connections)
- [Physician Accounts and Transactions](Physician_Accounts_and_Transactions.md) (8 shared connections)
- [Diagnosis Evaluation Tests](Diagnosis_Evaluation_Tests.md) (5 shared connections)
- [C-SSRS HTTP Tests](C-SSRS_HTTP_Tests.md) (3 shared connections)
- [PANSS Evaluation Tests](PANSS_Evaluation_Tests.md) (3 shared connections)
- [Patient Registration Tests](Patient_Registration_Tests.md) (3 shared connections)
- [Physician Admin Tests](Physician_Admin_Tests.md) (3 shared connections)
- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (2 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (1 shared connections)
- [Released Content Tests](Released_Content_Tests.md) (1 shared connections)
- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (1 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/accounts.py`
- `backend/tests/http/test_history.py`

## Audit Trail

- EXTRACTED: 55 (62%)
- INFERRED: 34 (38%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*