# create_patient

> 23 nodes

## Key Concepts

- **create_patient()** (16 connections) — `backend/src/x_insight/cases/patients.py`
- **list_patients()** (11 connections) — `backend/src/x_insight/cases/patients.py`
- **to_utc_z()** (10 connections) — `backend/src/x_insight/contracts.py`
- **PatientCreate** (5 connections) — `backend/src/x_insight/cases/patients.py`
- **_patient_payload()** (5 connections) — `backend/src/x_insight/cases/patients.py`
- **_encounter_payload()** (4 connections) — `backend/src/x_insight/cases/patients.py`
- **utc_now()** (3 connections) — `backend/src/x_insight/contracts.py`
- **datetime** (3 connections)
- **._letters_only()** (2 connections) — `backend/src/x_insight/cases/patients.py`
- **._patient_id_ascii_digits()** (2 connections) — `backend/src/x_insight/cases/patients.py`
- **Any** (2 connections)
- **field_validator** (2 connections)
- **JSONResponse** (2 connections)
- **Request** (2 connections)
- **UUID** (2 connections)
- **BaseModel** (1 connections)
- **ge** (1 connections)
- **get** (1 connections)
- **le** (1 connections)
- **post** (1 connections)
- **Query** (1 connections)
- **Return the current timezone-aware UTC time (server timestamps).** (1 connections) — `backend/src/x_insight/contracts.py`
- **Serialize a datetime as UTC ``...Z`` ISO-8601 text.** (1 connections) — `backend/src/x_insight/contracts.py`

## Relationships

- [routes.py](routes.py.md) (11 shared connections)
- [accounts.py](accounts.py.md) (6 shared connections)
- [_require_session](_require_session.md) (5 shared connections)
- [record_audit](record_audit.md) (2 shared connections)
- [store.py](store.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/cases/patients.py`
- `backend/src/x_insight/contracts.py`

## Audit Trail

- EXTRACTED: 52 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*