# Test Fixture Resets

> 18 nodes · cohesion 0.11

## Key Concepts

- **reset_all()** (11 connections) — `backend/src/x_insight/identity/throttle.py`
- **clean_cssrs()** (3 connections) — `backend/tests/http/test_cssrs.py`
- **clean_diagnosis()** (3 connections) — `backend/tests/http/test_diagnosis.py`
- **clean_drafts()** (3 connections) — `backend/tests/http/test_drafts.py`
- **clean_history()** (3 connections) — `backend/tests/http/test_history.py`
- **_clean_identity()** (3 connections) — `backend/tests/http/test_identity.py`
- **clean_panss()** (3 connections) — `backend/tests/http/test_panss.py`
- **clean_patients()** (3 connections) — `backend/tests/http/test_patients.py`
- **clean_accounts()** (3 connections) — `backend/tests/http/test_physicians.py`
- **Clear all throttle state (tests only).** (1 connections) — `backend/src/x_insight/identity/throttle.py`
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)

## Relationships

- [Released Content Tests](Released_Content_Tests.md) (1 shared connections)
- [Login Throttle and Clock](Login_Throttle_and_Clock.md) (1 shared connections)
- [C-SSRS HTTP Tests](C-SSRS_HTTP_Tests.md) (1 shared connections)
- [Diagnosis Evaluation Tests](Diagnosis_Evaluation_Tests.md) (1 shared connections)
- [Draft Lifecycle Tests](Draft_Lifecycle_Tests.md) (1 shared connections)
- [History HTTP Tests](History_HTTP_Tests.md) (1 shared connections)
- [Identity HTTP Tests](Identity_HTTP_Tests.md) (1 shared connections)
- [PANSS Evaluation Tests](PANSS_Evaluation_Tests.md) (1 shared connections)
- [Patient Registration Tests](Patient_Registration_Tests.md) (1 shared connections)
- [Physician Admin Tests](Physician_Admin_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/throttle.py`
- `backend/tests/http/test_cssrs.py`
- `backend/tests/http/test_diagnosis.py`
- `backend/tests/http/test_drafts.py`
- `backend/tests/http/test_history.py`
- `backend/tests/http/test_identity.py`
- `backend/tests/http/test_panss.py`
- `backend/tests/http/test_patients.py`
- `backend/tests/http/test_physicians.py`

## Audit Trail

- EXTRACTED: 26 (96%)
- INFERRED: 1 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*