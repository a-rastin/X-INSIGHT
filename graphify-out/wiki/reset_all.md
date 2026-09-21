# reset_all

> 14 nodes

## Key Concepts

- **reset_all()** (8 connections) — `backend/src/x_insight/identity/throttle.py`
- **clean_content()** (3 connections) — `backend/tests/http/test_content.py`
- **clean_diagnosis()** (3 connections) — `backend/tests/http/test_diagnosis.py`
- **clean_drafts()** (3 connections) — `backend/tests/http/test_drafts.py`
- **_clean_identity()** (3 connections) — `backend/tests/http/test_identity.py`
- **clean_patients()** (3 connections) — `backend/tests/http/test_patients.py`
- **clean_accounts()** (3 connections) — `backend/tests/http/test_physicians.py`
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **Clear all throttle state (tests only).** (1 connections) — `backend/src/x_insight/identity/throttle.py`

## Relationships

- [throttle.py](throttle.py.md) (1 shared connections)
- [test_content.py](test_content.py.md) (1 shared connections)
- [http/test_diagnosis.py](http-test_diagnosis.py.md) (1 shared connections)
- [physician](physician.md) (1 shared connections)
- [test_identity.py](test_identity.py.md) (1 shared connections)
- [test_patients.py](test_patients.py.md) (1 shared connections)
- [test_physicians.py](test_physicians.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/throttle.py`
- `backend/tests/http/test_content.py`
- `backend/tests/http/test_diagnosis.py`
- `backend/tests/http/test_drafts.py`
- `backend/tests/http/test_identity.py`
- `backend/tests/http/test_patients.py`
- `backend/tests/http/test_physicians.py`

## Audit Trail

- EXTRACTED: 19 (95%)
- INFERRED: 1 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*