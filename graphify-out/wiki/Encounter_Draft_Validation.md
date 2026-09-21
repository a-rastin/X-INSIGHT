# Encounter Draft Validation

> 55 nodes · cohesion 0.08

## Key Concepts

- **encounters.py** (47 connections) — `backend/src/x_insight/cases/encounters.py`
- **contracts.py** (24 connections) — `backend/src/x_insight/contracts.py`
- **patch_encounter()** (20 connections) — `backend/src/x_insight/cases/encounters.py`
- **history.py** (15 connections) — `backend/src/x_insight/cases/history.py`
- **discard_encounter()** (14 connections) — `backend/src/x_insight/cases/encounters.py`
- **to_utc_z()** (14 connections) — `backend/src/x_insight/contracts.py`
- **content_hash()** (10 connections) — `backend/src/x_insight/contracts.py`
- **_get_encounter()** (9 connections) — `backend/src/x_insight/cases/encounters.py`
- **Any** (9 connections)
- **_apply_diagnosis_ack()** (8 connections) — `backend/src/x_insight/cases/encounters.py`
- **list_encounters()** (8 connections) — `backend/src/x_insight/cases/encounters.py`
- **validate_and_stamp_effects()** (8 connections) — `backend/src/x_insight/cases/history.py`
- **validate_and_stamp_history()** (8 connections) — `backend/src/x_insight/cases/history.py`
- **canonical_json()** (8 connections) — `backend/src/x_insight/contracts.py`
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
- *... and 30 more nodes in this community*

## Relationships

- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (22 shared connections)
- [Patient and Session Routes](Patient_and_Session_Routes.md) (21 shared connections)
- [Physician Accounts and Transactions](Physician_Accounts_and_Transactions.md) (12 shared connections)
- [Diagnosis Evaluation Tests](Diagnosis_Evaluation_Tests.md) (6 shared connections)
- [C-SSRS Evaluation](C-SSRS_Evaluation.md) (3 shared connections)
- [Assessment Engine and PANSS Tests](Assessment_Engine_and_PANSS_Tests.md) (3 shared connections)
- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (3 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (3 shared connections)
- [Encounter Notes Endpoints](Encounter_Notes_Endpoints.md) (1 shared connections)
- [HTTP Contract Tests](HTTP_Contract_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/cases/encounters.py`
- `backend/src/x_insight/cases/history.py`
- `backend/src/x_insight/contracts.py`

## Audit Trail

- EXTRACTED: 195 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*