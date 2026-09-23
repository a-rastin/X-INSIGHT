# Cases Patients

> 30 nodes · cohesion 0.09

## Key Concepts

- **create_patient()** (16 connections) — `backend/src/x_insight/cases/patients.py`
- **patch_patient_phone()** (14 connections) — `backend/src/x_insight/cases/patients.py`
- **record_audit()** (14 connections) — `backend/src/x_insight/operations/audit.py`
- **list_patients()** (11 connections) — `backend/src/x_insight/cases/patients.py`
- **to_utc_z()** (8 connections) — `backend/src/x_insight/contracts.py`
- **_patient_payload()** (6 connections) — `backend/src/x_insight/cases/patients.py`
- **PatientCreate** (5 connections) — `backend/src/x_insight/cases/patients.py`
- **_encounter_payload()** (4 connections) — `backend/src/x_insight/cases/patients.py`
- **PatientPhonePatch** (4 connections) — `backend/src/x_insight/cases/patients.py`
- **JSONResponse** (3 connections)
- **Request** (3 connections)
- **UUID** (3 connections)
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
- **Query** (1 connections)
- **Update only the optional phone text (S12 slice 2, minimal). Mirrors the S07…** (1 connections) — `backend/src/x_insight/cases/patients.py`
- **S12 slice 2: physician-only optional phone text update. Phone is plain optional…** (1 connections) — `backend/src/x_insight/cases/patients.py`
- *... and 5 more nodes in this community*

## Relationships

- [Identity Hashing](Identity_Hashing.md) (12 shared connections)
- [MCP Server](MCP_Server.md) (11 shared connections)
- [Identity Accounts Contracts](Identity_Accounts_Contracts.md) (6 shared connections)
- [Reasoning Queue Proposal](Reasoning_Queue_Proposal.md) (3 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (1 shared connections)
- [Identity Store](Identity_Store.md) (1 shared connections)
- [Reasoning Queue Contracts](Reasoning_Queue_Contracts.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/cases/patients.py`
- `backend/src/x_insight/contracts.py`
- `backend/src/x_insight/operations/audit.py`

## Audit Trail

- EXTRACTED: 75 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*