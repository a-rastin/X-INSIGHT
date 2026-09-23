# Reasoning Queue Proposal

> 13 nodes · cohesion 0.17

## Key Concepts

- **transaction()** (68 connections) — `backend/src/x_insight/db.py`
- **try_assemble_proposal()** (8 connections) — `backend/src/x_insight/reasoning/proposal.py`
- **stop_and_revoke()** (7 connections) — `backend/src/x_insight/reasoning/mcp_host.py`
- **_applicability()** (3 connections) — `backend/src/x_insight/reasoning/proposal.py`
- **get_deployment_generation()** (3 connections) — `backend/src/x_insight/reasoning/queue.py`
- **set_deployment_generation()** (3 connections) — `backend/src/x_insight/reasoning/queue.py`
- **Any** (2 connections)
- **Connection** (1 connections)
- **Yield one transactional connection; callers commit/rollback together. Future…** (1 connections) — `backend/src/x_insight/db.py`
- **Revoke one scoped MCP grant idempotently (no-op when absent).** (1 connections) — `backend/src/x_insight/reasoning/mcp_host.py`
- **Attempt terminal proposal assembly for one run. Returns the succeeded proposal…** (1 connections) — `backend/src/x_insight/reasoning/proposal.py`
- **Return the current deployment generation (1 when uninitialized).** (1 connections) — `backend/src/x_insight/reasoning/queue.py`
- **Persist the deployment generation (tests/fencing rotation).** (1 connections) — `backend/src/x_insight/reasoning/queue.py`

## Relationships

- [Reasoning Coordinator Provider](Reasoning_Coordinator_Provider.md) (10 shared connections)
- [DDI Checker](DDI_Checker.md) (7 shared connections)
- [Identity Accounts Contracts](Identity_Accounts_Contracts.md) (7 shared connections)
- [Models Routes 3](Models_Routes_3.md) (7 shared connections)
- [Reasoning Queue Contracts](Reasoning_Queue_Contracts.md) (7 shared connections)
- [Reasoning Routes](Reasoning_Routes.md) (6 shared connections)
- [Cases Encounters](Cases_Encounters.md) (5 shared connections)
- [Identity Hashing](Identity_Hashing.md) (5 shared connections)
- [Cases Patients](Cases_Patients.md) (3 shared connections)
- [DDI Publish Tests](DDI_Publish_Tests.md) (3 shared connections)
- [Models Routes 2](Models_Routes_2.md) (3 shared connections)
- [MCP Server](MCP_Server.md) (2 shared connections)

## Source Files

- `backend/src/x_insight/db.py`
- `backend/src/x_insight/reasoning/mcp_host.py`
- `backend/src/x_insight/reasoning/proposal.py`
- `backend/src/x_insight/reasoning/queue.py`

## Audit Trail

- EXTRACTED: 87 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*