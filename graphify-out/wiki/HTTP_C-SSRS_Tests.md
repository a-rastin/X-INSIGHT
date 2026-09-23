# HTTP C-SSRS Tests

> 13 nodes · cohesion 0.36

## Key Concepts

- **physician()** (39 connections) — `backend/src/x_insight/identity/accounts.py`
- **http/test_cssrs.py** (18 connections) — `backend/tests/http/test_cssrs.py`
- **_setup_encounter()** (7 connections) — `backend/tests/http/test_cssrs.py`
- **test_invalid_cssrs_rejected()** (5 connections) — `backend/tests/http/test_cssrs.py`
- **test_period_validation_and_persistence()** (5 connections) — `backend/tests/http/test_cssrs.py`
- **test_skip_persists_and_resumes()** (5 connections) — `backend/tests/http/test_cssrs.py`
- **draft_headers()** (4 connections) — `backend/tests/http/test_cssrs.py`
- **encounter_body()** (4 connections) — `backend/tests/http/test_cssrs.py`
- **create_patient()** (3 connections) — `backend/tests/http/test_cssrs.py`
- **create_physician()** (3 connections) — `backend/tests/http/test_cssrs.py`
- **patient_headers()** (3 connections) — `backend/tests/http/test_cssrs.py`
- **login()** (2 connections) — `backend/tests/http/test_cssrs.py`
- **S11 slice 1 (RED): C-SSRS autosave validation + skip resume (T1). SYNTHETIC…** (1 connections) — `backend/tests/http/test_cssrs.py`

## Relationships

- [HTTP Drafts Tests](HTTP_Drafts_Tests.md) (9 shared connections)
- [Identity Accounts Contracts](Identity_Accounts_Contracts.md) (8 shared connections)
- [HTTP History Tests](HTTP_History_Tests.md) (8 shared connections)
- [HTTP Diagnosis Tests](HTTP_Diagnosis_Tests.md) (5 shared connections)
- [Assessment PANSS Tests](Assessment_PANSS_Tests.md) (3 shared connections)
- [HTTP Patients Tests](HTTP_Patients_Tests.md) (3 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [MCP Server](MCP_Server.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [Identity Throttle Clock](Identity_Throttle_Clock.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/accounts.py`
- `backend/tests/http/test_cssrs.py`

## Audit Trail

- EXTRACTED: 40 (56%)
- INFERRED: 31 (44%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*