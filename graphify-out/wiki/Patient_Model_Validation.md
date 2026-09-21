# Patient Model Validation

> 7 nodes · cohesion 0.33

## Key Concepts

- **PatientCreate** (5 connections) — `backend/src/x_insight/cases/patients.py`
- **PatientPhonePatch** (4 connections) — `backend/src/x_insight/cases/patients.py`
- **._letters_only()** (2 connections) — `backend/src/x_insight/cases/patients.py`
- **._patient_id_ascii_digits()** (2 connections) — `backend/src/x_insight/cases/patients.py`
- **BaseModel** (2 connections)
- **field_validator** (2 connections)
- **S12 slice 2: physician-only optional phone text update. Phone is plain optional…** (1 connections) — `backend/src/x_insight/cases/patients.py`

## Relationships

- [Patient and Session Routes](Patient_and_Session_Routes.md) (2 shared connections)
- [App Wiring and Persistence](App_Wiring_and_Persistence.md) (2 shared connections)

## Source Files

- `backend/src/x_insight/cases/patients.py`

## Audit Trail

- EXTRACTED: 11 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*