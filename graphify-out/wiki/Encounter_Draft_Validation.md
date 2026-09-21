# Encounter Draft Validation

> 47 nodes · cohesion 0.09

## Key Concepts

- **encounters.py** (47 connections) — `backend/src/x_insight/cases/encounters.py`
- **patch_encounter()** (20 connections) — `backend/src/x_insight/cases/encounters.py`
- **history.py** (15 connections) — `backend/src/x_insight/cases/history.py`
- **discard_encounter()** (14 connections) — `backend/src/x_insight/cases/encounters.py`
- **parse_if_match()** (10 connections) — `backend/src/x_insight/contracts.py`
- **_get_encounter()** (9 connections) — `backend/src/x_insight/cases/encounters.py`
- **Any** (9 connections)
- **_apply_diagnosis_ack()** (8 connections) — `backend/src/x_insight/cases/encounters.py`
- **list_encounters()** (8 connections) — `backend/src/x_insight/cases/encounters.py`
- **validate_and_stamp_effects()** (8 connections) — `backend/src/x_insight/cases/history.py`
- **validate_and_stamp_history()** (8 connections) — `backend/src/x_insight/cases/history.py`
- **utc_now()** (8 connections) — `backend/src/x_insight/contracts.py`
- **_payload()** (7 connections) — `backend/src/x_insight/cases/encounters.py`
- **_apply_cssrs_validation()** (5 connections) — `backend/src/x_insight/cases/encounters.py`
- **_apply_panss_validation()** (5 connections) — `backend/src/x_insight/cases/encounters.py`
- **UUID** (5 connections)
- **_load_released_definition()** (5 connections) — `backend/src/x_insight/cases/history.py`
- **Any** (5 connections)
- **validate_history_reconciliation()** (5 connections) — `backend/src/x_insight/cases/history.py`
- **validate_medications()** (5 connections) — `backend/src/x_insight/cases/history.py`
- **_apply_effects_validation()** (4 connections) — `backend/src/x_insight/cases/encounters.py`
- **_apply_history_validation()** (4 connections) — `backend/src/x_insight/cases/encounters.py`
- **_apply_medications_guard()** (4 connections) — `backend/src/x_insight/cases/encounters.py`
- **_apply_reconciliation_guard()** (4 connections) — `backend/src/x_insight/cases/encounters.py`
- **DiscardRequest** (4 connections) — `backend/src/x_insight/cases/encounters.py`
- *... and 22 more nodes in this community*

## Relationships

- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (13 shared connections)
- [Patient Registration](Patient_Registration.md) (12 shared connections)
- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (10 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (7 shared connections)
- [Physician Accounts and Transactions](Physician_Accounts_and_Transactions.md) (7 shared connections)
- [C-SSRS Evaluation](C-SSRS_Evaluation.md) (3 shared connections)
- [Diagnosis Evaluation Tests](Diagnosis_Evaluation_Tests.md) (3 shared connections)
- [PANSS Evaluation Tests](PANSS_Evaluation_Tests.md) (2 shared connections)
- [Database Engine and Readiness](Database_Engine_and_Readiness.md) (2 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/cases/encounters.py`
- `backend/src/x_insight/cases/history.py`
- `backend/src/x_insight/contracts.py`

## Audit Trail

- EXTRACTED: 160 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*