# Identity Throttle C-SSRS

> 14 nodes · cohesion 0.14

## Key Concepts

- **reset_all()** (8 connections) — `backend/src/x_insight/identity/throttle.py`
- **clean_cssrs()** (3 connections) — `backend/tests/http/test_cssrs.py`
- **clean_diagnosis()** (3 connections) — `backend/tests/http/test_diagnosis.py`
- **clean_drafts()** (3 connections) — `backend/tests/http/test_drafts.py`
- **clean_history()** (3 connections) — `backend/tests/http/test_history.py`
- **clean_panss()** (3 connections) — `backend/tests/http/test_panss.py`
- **clean_patients()** (3 connections) — `backend/tests/http/test_patients.py`
- **Clear all throttle state (tests only).** (1 connections) — `backend/src/x_insight/identity/throttle.py`
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)
- **fixture** (1 connections)

## Relationships

- [Identity Throttle Clock](Identity_Throttle_Clock.md) (1 shared connections)
- [HTTP C-SSRS Tests](HTTP_C-SSRS_Tests.md) (1 shared connections)
- [HTTP Diagnosis Tests](HTTP_Diagnosis_Tests.md) (1 shared connections)
- [HTTP Drafts Tests](HTTP_Drafts_Tests.md) (1 shared connections)
- [MCP Server](MCP_Server.md) (1 shared connections)
- [Assessment PANSS Tests](Assessment_PANSS_Tests.md) (1 shared connections)
- [HTTP Patients Tests](HTTP_Patients_Tests.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/throttle.py`
- `backend/tests/http/test_cssrs.py`
- `backend/tests/http/test_diagnosis.py`
- `backend/tests/http/test_drafts.py`
- `backend/tests/http/test_history.py`
- `backend/tests/http/test_panss.py`
- `backend/tests/http/test_patients.py`

## Audit Trail

- EXTRACTED: 20 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*