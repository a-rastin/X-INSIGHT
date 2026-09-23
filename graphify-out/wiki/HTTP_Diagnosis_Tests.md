# HTTP Diagnosis Tests

> 15 nodes · cohesion 0.42

## Key Concepts

- **http/test_diagnosis.py** (22 connections) — `backend/tests/http/test_diagnosis.py`
- **test_answers_change_invalidates_prior_ack()** (10 connections) — `backend/tests/http/test_diagnosis.py`
- **test_below_threshold_without_ack_stays_unacknowledged()** (9 connections) — `backend/tests/http/test_diagnosis.py`
- **test_forged_warning_ack_rejected()** (9 connections) — `backend/tests/http/test_diagnosis.py`
- **create_patient()** (7 connections) — `backend/tests/http/test_diagnosis.py`
- **create_physician()** (7 connections) — `backend/tests/http/test_diagnosis.py`
- **test_bypass_without_reason_succeeds_and_survives_resume()** (7 connections) — `backend/tests/http/test_diagnosis.py`
- **test_forged_bypass_rejected()** (7 connections) — `backend/tests/http/test_diagnosis.py`
- **draft_headers()** (6 connections) — `backend/tests/http/test_diagnosis.py`
- **encounter_body()** (6 connections) — `backend/tests/http/test_diagnosis.py`
- **login()** (6 connections) — `backend/tests/http/test_diagnosis.py`
- **synthetic_below_threshold_answers()** (5 connections) — `backend/tests/http/test_diagnosis.py`
- **patient_headers()** (3 connections) — `backend/tests/http/test_diagnosis.py`
- **S09 slice 3 (RED): below-threshold warning acknowledgment over autosave…** (1 connections) — `backend/tests/http/test_diagnosis.py`
- **SYNTHETIC: 2 domains, no shared 1-month phase; A-E fail on paper.** (1 connections) — `backend/tests/http/test_diagnosis.py`

## Relationships

- [HTTP C-SSRS Tests](HTTP_C-SSRS_Tests.md) (5 shared connections)
- [Assessment Diagnosis Tests](Assessment_Diagnosis_Tests.md) (3 shared connections)
- [Shared HTTP Contracts](Shared_HTTP_Contracts.md) (2 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [MCP Server](MCP_Server.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [Identity Throttle Clock](Identity_Throttle_Clock.md) (1 shared connections)
- [Identity Throttle C-SSRS](Identity_Throttle_C-SSRS.md) (1 shared connections)

## Source Files

- `backend/tests/http/test_diagnosis.py`

## Audit Trail

- EXTRACTED: 57 (92%)
- INFERRED: 5 (8%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*