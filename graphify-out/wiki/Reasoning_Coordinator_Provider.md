# Reasoning Coordinator Provider

> 33 nodes · cohesion 0.12

## Key Concepts

- **coordinator.py** (51 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **execute_claimed_question()** (26 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **Any** (16 connections)
- **CoordinatorError** (10 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_estimate_via_mcp()** (8 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_resolve_provider()** (7 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **decrypt_api_key()** (7 connections) — `backend/src/x_insight/reasoning/provider_config.py`
- **_load_claim_context()** (5 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_stored_success()** (5 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_verify_artifact_for_commit()** (5 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_insert_grant()** (4 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_payload_from_mcp_result()** (4 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_persist_artifact()** (4 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_pinned_query()** (4 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **render_section()** (4 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_run_local_effective()** (4 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_scoped_projection()** (4 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **bridge()** (3 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_network_contract()** (3 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_tool_declaration()** (3 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **Exception** (1 connections)
- **Single-question coordinator (S45 slice 1: T1/T8 end to end, T5-T7 inside). One…** (1 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **Return the pinned query, defaulting to the last-node marginal. The S45…** (1 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **Render a deterministic section from stored result + accepted CPTs only. Never…** (1 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **Resolve base_url/api_key/model from the active provider revision. Falls back…** (1 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- *... and 8 more nodes in this community*

## Relationships

- [Reasoning Queue Proposal](Reasoning_Queue_Proposal.md) (10 shared connections)
- [Reasoning Provider](Reasoning_Provider.md) (7 shared connections)
- [Reasoning Coordinator 2](Reasoning_Coordinator_2.md) (6 shared connections)
- [DDI Checker](DDI_Checker.md) (4 shared connections)
- [Model CPT Inference Tests Validation](Model_CPT_Inference_Tests_Validation.md) (4 shared connections)
- [Models Inference](Models_Inference.md) (3 shared connections)
- [Reasoning Queue Contracts](Reasoning_Queue_Contracts.md) (3 shared connections)
- [Provider Config](Provider_Config.md) (3 shared connections)
- [Worker Recovery Tests](Worker_Recovery_Tests.md) (3 shared connections)
- [MCP Server](MCP_Server.md) (2 shared connections)
- [Model CPT Inference Tests 2](Model_CPT_Inference_Tests_2.md) (2 shared connections)
- [MCP Scoped Transport Tests](MCP_Scoped_Transport_Tests.md) (2 shared connections)

## Source Files

- `backend/src/x_insight/reasoning/coordinator.py`
- `backend/src/x_insight/reasoning/provider_config.py`

## Audit Trail

- EXTRACTED: 122 (97%)
- INFERRED: 4 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*