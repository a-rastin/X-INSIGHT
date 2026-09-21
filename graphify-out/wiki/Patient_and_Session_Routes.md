# Patient and Session Routes

> 40 nodes · cohesion 0.10

## Key Concepts

- **_require_session()** (28 connections) — `backend/src/x_insight/identity/routes.py`
- **transaction()** (25 connections) — `backend/src/x_insight/db.py`
- **_check_csrf()** (17 connections) — `backend/src/x_insight/identity/routes.py`
- **record_audit()** (17 connections) — `backend/src/x_insight/operations/audit.py`
- **create_patient()** (16 connections) — `backend/src/x_insight/cases/patients.py`
- **change_password()** (15 connections) — `backend/src/x_insight/identity/routes.py`
- **_request_id()** (15 connections) — `backend/src/x_insight/identity/routes.py`
- **patch_patient_phone()** (14 connections) — `backend/src/x_insight/cases/patients.py`
- **list_patients()** (11 connections) — `backend/src/x_insight/cases/patients.py`
- **Request** (11 connections)
- **logout()** (10 connections) — `backend/src/x_insight/identity/routes.py`
- **update_preferences()** (9 connections) — `backend/src/x_insight/identity/routes.py`
- **JSONResponse** (8 connections)
- **me()** (7 connections) — `backend/src/x_insight/identity/routes.py`
- **_patient_payload()** (6 connections) — `backend/src/x_insight/cases/patients.py`
- **_encounter_payload()** (4 connections) — `backend/src/x_insight/cases/patients.py`
- **JSONResponse** (3 connections)
- **Request** (3 connections)
- **UUID** (3 connections)
- **post** (3 connections)
- **_session_token()** (3 connections) — `backend/src/x_insight/identity/routes.py`
- **Any** (2 connections)
- **Any** (2 connections)
- **ge** (1 connections)
- **get** (1 connections)
- *... and 15 more nodes in this community*

## Relationships

- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (29 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (21 shared connections)
- [Physician Accounts and Transactions](Physician_Accounts_and_Transactions.md) (17 shared connections)
- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (15 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (3 shared connections)
- [Patient Model Validation](Patient_Model_Validation.md) (2 shared connections)
- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (2 shared connections)
- [History Content Endpoints](History_Content_Endpoints.md) (2 shared connections)

## Source Files

- `backend/src/x_insight/cases/patients.py`
- `backend/src/x_insight/db.py`
- `backend/src/x_insight/identity/routes.py`
- `backend/src/x_insight/operations/audit.py`

## Audit Trail

- EXTRACTED: 170 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*