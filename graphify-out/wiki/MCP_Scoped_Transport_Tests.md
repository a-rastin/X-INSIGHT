# MCP Scoped Transport Tests

> 72 nodes · cohesion 0.05

## Key Concepts

- **test_scoped_transport.py** (51 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **build_scoped_server_params()** (15 connections) — `backend/src/x_insight/reasoning/mcp_host.py`
- **_run_denial()** (15 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_seed_slice2_valid_grant()** (15 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **test_slice3_successive_question_rebinding_revokes_old()** (8 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **test_slice3_stderr_stdout_separation()** (7 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_s3_seed_notes_encounter()** (6 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_s3_seed_successive_questions()** (6 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_s3_seed_two_isolated_patients()** (6 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **test_slice4_transport_kill_then_cleanup_revokes()** (6 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_call_via_real_stdio()** (5 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_s3_insert_run_question_grant()** (5 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_s3_parse_success_payload()** (5 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_s4_call_with_extra_env()** (5 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **test_slice3_concurrent_patient_isolation()** (5 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **test_slice3_notes_excluded_from_projection()** (5 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **test_slice4_database_failure_bounded()** (5 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **test_slice4_oversized_projection_bounded()** (5 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_assert_no_leak()** (4 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_assert_safe_denial()** (4 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_list_and_call_via_real_stdio()** (4 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_s3_insert_actor()** (4 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_s3_insert_patient_encounter()** (4 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_s3_read_one_via_real_stdio()** (4 connections) — `backend/tests/mcp/test_scoped_transport.py`
- **_s3_run_denial()** (4 connections) — `backend/tests/mcp/test_scoped_transport.py`
- *... and 47 more nodes in this community*

## Relationships

- [MCP Server](MCP_Server.md) (4 shared connections)
- [Reasoning Coordinator Provider](Reasoning_Coordinator_Provider.md) (2 shared connections)
- [MCP Builder Connections 4](MCP_Builder_Connections_4.md) (2 shared connections)
- [Reasoning Queue Proposal](Reasoning_Queue_Proposal.md) (2 shared connections)
- [Database Engine Session](Database_Engine_Session.md) (1 shared connections)
- [Provider Estimation Tests 2](Provider_Estimation_Tests_2.md) (1 shared connections)
- [MCP Builder Evaluation 4](MCP_Builder_Evaluation_4.md) (1 shared connections)
- [Identity Store](Identity_Store.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [DDI Checker](DDI_Checker.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/reasoning/mcp_host.py`
- `backend/tests/mcp/test_scoped_transport.py`

## Audit Trail

- EXTRACTED: 153 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*