# Worker Snapshots Tests

> 37 nodes · cohesion 0.17

## Key Concepts

- **test_snapshots.py** (37 connections) — `backend/tests/worker/test_snapshots.py`
- **_mutation_headers()** (14 connections) — `backend/tests/worker/test_snapshots.py`
- **_create_sentinel_patient()** (11 connections) — `backend/tests/worker/test_snapshots.py`
- **_make_physician()** (11 connections) — `backend/tests/worker/test_snapshots.py`
- **test_fingerprint_note_vs_analytical_slice3()** (11 connections) — `backend/tests/worker/test_snapshots.py`
- **test_forbid_cross_question_inputs_slice4()** (11 connections) — `backend/tests/worker/test_snapshots.py`
- **test_gate_ready_applicable_clarification_slice4()** (11 connections) — `backend/tests/worker/test_snapshots.py`
- **test_snapshot_immutable_after_changes_slice3()** (11 connections) — `backend/tests/worker/test_snapshots.py`
- **_login()** (10 connections) — `backend/tests/worker/test_snapshots.py`
- **test_mapping_rejects_notes_regardless_of_prompt_slice2()** (10 connections) — `backend/tests/worker/test_snapshots.py`
- **test_projection_exact_variables_slice2()** (10 connections) — `backend/tests/worker/test_snapshots.py`
- **_current_revision()** (9 connections) — `backend/tests/worker/test_snapshots.py`
- **_clinical_draft()** (8 connections) — `backend/tests/worker/test_snapshots.py`
- **test_run_freezes_clinical_facts_and_excludes_pii_and_notes()** (8 connections) — `backend/tests/worker/test_snapshots.py`
- **test_run_start_guards_auth_ownership_and_body()** (8 connections) — `backend/tests/worker/test_snapshots.py`
- **test_stale_or_invalid_revision_fails_without_partial_snapshot()** (7 connections) — `backend/tests/worker/test_snapshots.py`
- **_insert_synthetic_bundle()** (6 connections) — `backend/tests/worker/test_snapshots.py`
- **_flipped_slice3_draft()** (5 connections) — `backend/tests/worker/test_snapshots.py`
- **_gate_draft()** (4 connections) — `backend/tests/worker/test_snapshots.py`
- **_insert_mapping_bundle()** (4 connections) — `backend/tests/worker/test_snapshots.py`
- **_mapping_draft_with_states()** (4 connections) — `backend/tests/worker/test_snapshots.py`
- **_start_run()** (4 connections) — `backend/tests/worker/test_snapshots.py`
- **_valid_slice2_mappings()** (4 connections) — `backend/tests/worker/test_snapshots.py`
- **_gate_question()** (3 connections) — `backend/tests/worker/test_snapshots.py`
- **_get_run()** (3 connections) — `backend/tests/worker/test_snapshots.py`
- *... and 12 more nodes in this community*

## Relationships

- [MCP Server](MCP_Server.md) (2 shared connections)
- [Cases Notes](Cases_Notes.md) (1 shared connections)
- [Test Fixture Setup](Test_Fixture_Setup.md) (1 shared connections)
- [HTTP Contracts Tests](HTTP_Contracts_Tests.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)
- [Knowledge Base App](Knowledge_Base_App.md) (1 shared connections)
- [HTTP DDI Tests](HTTP_DDI_Tests.md) (1 shared connections)

## Source Files

- `backend/tests/worker/test_snapshots.py`

## Audit Trail

- EXTRACTED: 125 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*