# Worker Recovery Tests

> 48 nodes · cohesion 0.10

## Key Concepts

- **test_recovery.py** (39 connections) — `backend/tests/worker/test_recovery.py`
- **test_stage_retry_reuses_cpts_and_result_without_new_posts()** (20 connections) — `backend/tests/worker/test_recovery.py`
- **test_manual_retry_starts_new_bounded_batch_without_repeating_q1()** (18 connections) — `backend/tests/worker/test_recovery.py`
- **test_timeout_invalid_ratelimit_exhausts_three_attempts()** (17 connections) — `backend/tests/worker/test_recovery.py`
- **_start_provider()** (8 connections) — `backend/tests/worker/test_recovery.py`
- **_start_provider_fail_then_succeed()** (8 connections) — `backend/tests/worker/test_recovery.py`
- **_body_question_key()** (7 connections) — `backend/tests/worker/test_recovery.py`
- **_mutation_headers()** (7 connections) — `backend/tests/worker/test_recovery.py`
- **_start_provider_always_valid()** (7 connections) — `backend/tests/worker/test_recovery.py`
- **_clinical_draft()** (6 connections) — `backend/tests/worker/test_recovery.py`
- **_create_sentinel_patient()** (5 connections) — `backend/tests/worker/test_recovery.py`
- **_drain_with_backoff()** (5 connections) — `backend/tests/worker/test_recovery.py`
- **_insert_provider_config()** (5 connections) — `backend/tests/worker/test_recovery.py`
- **_invalid_cpt_payload()** (5 connections) — `backend/tests/worker/test_recovery.py`
- **_make_physician()** (5 connections) — `backend/tests/worker/test_recovery.py`
- **_make_question()** (5 connections) — `backend/tests/worker/test_recovery.py`
- **_mutated_clinical_draft()** (5 connections) — `backend/tests/worker/test_recovery.py`
- **_start_run()** (5 connections) — `backend/tests/worker/test_recovery.py`
- **_synthetic_cpt_payload()** (5 connections) — `backend/tests/worker/test_recovery.py`
- **_current_revision()** (4 connections) — `backend/tests/worker/test_recovery.py`
- **_get_run()** (4 connections) — `backend/tests/worker/test_recovery.py`
- **_insert_bundle()** (4 connections) — `backend/tests/worker/test_recovery.py`
- **_login()** (4 connections) — `backend/tests/worker/test_recovery.py`
- **clean_recovery()** (3 connections) — `backend/tests/worker/test_recovery.py`
- **Any** (3 connections)
- *... and 23 more nodes in this community*

## Relationships

- [DDI Checker](DDI_Checker.md) (3 shared connections)
- [Worker Single Question Tests](Worker_Single_Question_Tests.md) (3 shared connections)
- [Reasoning Retry](Reasoning_Retry.md) (3 shared connections)
- [Reasoning Coordinator Provider](Reasoning_Coordinator_Provider.md) (3 shared connections)
- [MCP Server](MCP_Server.md) (2 shared connections)
- [Cases Notes](Cases_Notes.md) (1 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (1 shared connections)
- [Provider Config](Provider_Config.md) (1 shared connections)

## Source Files

- `backend/tests/worker/test_recovery.py`

## Audit Trail

- EXTRACTED: 121 (93%)
- INFERRED: 9 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*