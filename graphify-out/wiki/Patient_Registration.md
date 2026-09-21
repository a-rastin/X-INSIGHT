# Patient Registration

> 35 nodes · cohesion 0.09

## Key Concepts

- **patients.py** (34 connections) — `backend/src/x_insight/cases/patients.py`
- **record_audit()** (17 connections) — `backend/src/x_insight/operations/audit.py`
- **create_patient()** (16 connections) — `backend/src/x_insight/cases/patients.py`
- **patch_patient_phone()** (14 connections) — `backend/src/x_insight/cases/patients.py`
- **to_utc_z()** (14 connections) — `backend/src/x_insight/contracts.py`
- **list_patients()** (11 connections) — `backend/src/x_insight/cases/patients.py`
- **_patient_payload()** (6 connections) — `backend/src/x_insight/cases/patients.py`
- **PatientCreate** (5 connections) — `backend/src/x_insight/cases/patients.py`
- **_encounter_payload()** (4 connections) — `backend/src/x_insight/cases/patients.py`
- **PatientPhonePatch** (4 connections) — `backend/src/x_insight/cases/patients.py`
- **pydantic** (4 connections)
- **JSONResponse** (3 connections)
- **Request** (3 connections)
- **UUID** (3 connections)
- **sqlalchemy_exc** (3 connections)
- **._letters_only()** (2 connections) — `backend/src/x_insight/cases/patients.py`
- **._patient_id_ascii_digits()** (2 connections) — `backend/src/x_insight/cases/patients.py`
- **Any** (2 connections)
- **BaseModel** (2 connections)
- **field_validator** (2 connections)
- **ge** (1 connections)
- **get** (1 connections)
- **le** (1 connections)
- **patch** (1 connections)
- **post** (1 connections)
- *... and 10 more nodes in this community*

## Relationships

- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (22 shared connections)
- [Encounter Draft Validation](Encounter_Draft_Validation.md) (12 shared connections)
- [Physician Accounts and Transactions](Physician_Accounts_and_Transactions.md) (11 shared connections)
- [Assessment Content Endpoints](Assessment_Content_Endpoints.md) (6 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (5 shared connections)
- [MCP Evaluation Harness](MCP_Evaluation_Harness.md) (1 shared connections)
- [App Middleware and Errors](App_Middleware_and_Errors.md) (1 shared connections)
- [Database Engine and Readiness](Database_Engine_and_Readiness.md) (1 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/cases/patients.py`
- `backend/src/x_insight/contracts.py`
- `backend/src/x_insight/operations/audit.py`

## Audit Trail

- EXTRACTED: 113 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*