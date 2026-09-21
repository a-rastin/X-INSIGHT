# verify_password

> 8 nodes

## Key Concepts

- **verify_password()** (10 connections) — `backend/src/x_insight/identity/hashing.py`
- **PatientCreate** (5 connections) — `backend/src/x_insight/cases/patients.py`
- **test_admin_password_is_hashed()** (3 connections) — `backend/tests/http/test_identity.py`
- **._letters_only()** (2 connections) — `backend/src/x_insight/cases/patients.py`
- **._patient_id_ascii_digits()** (2 connections) — `backend/src/x_insight/cases/patients.py`
- **field_validator** (2 connections)
- **BaseModel** (1 connections)
- **Compare an exact password against a stored hash; False on malformed.** (1 connections) — `backend/src/x_insight/identity/hashing.py`

## Relationships

- [patients.py](patients.py.md) (4 shared connections)
- [routes.py](routes.py.md) (4 shared connections)
- [accounts.py](accounts.py.md) (2 shared connections)
- [store.py](store.py.md) (1 shared connections)
- [test_identity.py](test_identity.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/cases/patients.py`
- `backend/src/x_insight/identity/hashing.py`
- `backend/tests/http/test_identity.py`

## Audit Trail

- EXTRACTED: 19 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*