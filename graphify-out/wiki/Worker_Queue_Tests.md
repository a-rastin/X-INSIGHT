# Worker Queue Tests

> 50 nodes · cohesion 0.10

## Key Concepts

- **test_queue.py** (37 connections) — `backend/tests/worker/test_queue.py`
- **test_global_admission_single_question_per_run()** (15 connections) — `backend/tests/worker/test_queue.py`
- **test_short_claim_lease_heartbeat_persistent_admission()** (15 connections) — `backend/tests/worker/test_queue.py`
- **test_expired_lease_reclaimed_old_token_cannot_commit()** (13 connections) — `backend/tests/worker/test_queue.py`
- **_mutation_headers()** (12 connections) — `backend/tests/worker/test_queue.py`
- **test_restart_retains_attempts_and_terminal_artifacts()** (11 connections) — `backend/tests/worker/test_queue.py`
- **test_simultaneous_triggers_cannot_create_two_active_generations()** (11 connections) — `backend/tests/worker/test_queue.py`
- **_login()** (10 connections) — `backend/tests/worker/test_queue.py`
- **_make_physician()** (10 connections) — `backend/tests/worker/test_queue.py`
- **test_run_creation_and_first_job_atomic_and_fingerprint_reuse()** (10 connections) — `backend/tests/worker/test_queue.py`
- **test_saturation_busy_without_deletion()** (10 connections) — `backend/tests/worker/test_queue.py`
- **_create_sentinel_patient()** (9 connections) — `backend/tests/worker/test_queue.py`
- **_insert_synthetic_bundle()** (9 connections) — `backend/tests/worker/test_queue.py`
- **_s4_start_run()** (9 connections) — `backend/tests/worker/test_queue.py`
- **_clinical_draft()** (8 connections) — `backend/tests/worker/test_queue.py`
- **_current_revision()** (8 connections) — `backend/tests/worker/test_queue.py`
- **_s3_create_queued_run()** (8 connections) — `backend/tests/worker/test_queue.py`
- **test_fair_rotation_across_physicians_then_fifo()** (8 connections) — `backend/tests/worker/test_queue.py`
- **_s2_start_run()** (5 connections) — `backend/tests/worker/test_queue.py`
- **_assert_first_job()** (4 connections) — `backend/tests/worker/test_queue.py`
- **_s2_is_claimed()** (3 connections) — `backend/tests/worker/test_queue.py`
- **_s2_truncate_queue_tables()** (3 connections) — `backend/tests/worker/test_queue.py`
- **_s4_attempt_evidence()** (3 connections) — `backend/tests/worker/test_queue.py`
- **_s4_commit_rejected()** (3 connections) — `backend/tests/worker/test_queue.py`
- **_s4_run_once_keys()** (3 connections) — `backend/tests/worker/test_queue.py`
- *... and 25 more nodes in this community*

## Relationships

- [Reasoning Retry](Reasoning_Retry.md) (6 shared connections)
- [MCP Server](MCP_Server.md) (2 shared connections)
- [Worker Single Question Tests](Worker_Single_Question_Tests.md) (1 shared connections)
- [Cases Notes](Cases_Notes.md) (1 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (1 shared connections)
- [Reasoning Queue Contracts](Reasoning_Queue_Contracts.md) (1 shared connections)

## Source Files

- `backend/tests/worker/test_queue.py`

## Audit Trail

- EXTRACTED: 130 (90%)
- INFERRED: 15 (10%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*