# Reasoning Queue Contracts

> 30 nodes · cohesion 0.13

## Key Concepts

- **queue.py** (29 connections) — `backend/src/x_insight/reasoning/queue.py`
- **datetime** (12 connections)
- **complete_job()** (10 connections) — `backend/src/x_insight/reasoning/queue.py`
- **now_utc()** (9 connections) — `backend/src/x_insight/reasoning/queue.py`
- **Any** (9 connections)
- **claim_next_job()** (8 connections) — `backend/src/x_insight/reasoning/queue.py`
- **record_attempt()** (8 connections) — `backend/src/x_insight/reasoning/queue.py`
- **reschedule_for_retry()** (7 connections) — `backend/src/x_insight/reasoning/queue.py`
- **heartbeat()** (6 connections) — `backend/src/x_insight/reasoning/queue.py`
- **first_eligible_question()** (5 connections) — `backend/src/x_insight/reasoning/queue.py`
- **lease_deadline_from()** (5 connections) — `backend/src/x_insight/reasoning/queue.py`
- **_current_generation()** (4 connections) — `backend/src/x_insight/reasoning/queue.py`
- **_error_json()** (4 connections) — `backend/src/x_insight/reasoning/queue.py`
- **_outcome_text()** (4 connections) — `backend/src/x_insight/reasoning/queue.py`
- **utc_now()** (3 connections) — `backend/src/x_insight/contracts.py`
- **_default_now()** (3 connections) — `backend/src/x_insight/reasoning/queue.py`
- **reset_now_fn()** (3 connections) — `backend/src/x_insight/reasoning/queue.py`
- **set_now_fn()** (3 connections) — `backend/src/x_insight/reasoning/queue.py`
- **Return the current timezone-aware UTC time (server timestamps).** (1 connections) — `backend/src/x_insight/contracts.py`
- **Durable leased job queue (S44 slices 1-4, extensible).** (1 connections) — `backend/src/x_insight/reasoning/queue.py`
- **Return (question_key, ordinal) for the first ready question. Triples are in…** (1 connections) — `backend/src/x_insight/reasoning/queue.py`
- **Claim one queued job under the global provider-slot cap. Single short…** (1 connections) — `backend/src/x_insight/reasoning/queue.py`
- **Park a still-claimed job back to ``queued`` with future eligibility. Single…** (1 connections) — `backend/src/x_insight/reasoning/queue.py`
- **Extend a live lease; None on unknown token or expired lease.** (1 connections) — `backend/src/x_insight/reasoning/queue.py`
- **Persist one provider attempt; return its 1-based attempt_index.** (1 connections) — `backend/src/x_insight/reasoning/queue.py`
- *... and 5 more nodes in this community*

## Relationships

- [DDI Checker](DDI_Checker.md) (7 shared connections)
- [Reasoning Queue Proposal](Reasoning_Queue_Proposal.md) (7 shared connections)
- [Reasoning Retry](Reasoning_Retry.md) (4 shared connections)
- [Reasoning Snapshots](Reasoning_Snapshots.md) (3 shared connections)
- [Reasoning Coordinator Provider](Reasoning_Coordinator_Provider.md) (3 shared connections)
- [MCP Server](MCP_Server.md) (2 shared connections)
- [Models Inference](Models_Inference.md) (1 shared connections)
- [Cases Notes](Cases_Notes.md) (1 shared connections)
- [Database Migrations](Database_Migrations.md) (1 shared connections)
- [Database Engine Session](Database_Engine_Session.md) (1 shared connections)
- [Worker Queue Tests](Worker_Queue_Tests.md) (1 shared connections)
- [Cases Patients](Cases_Patients.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/contracts.py`
- `backend/src/x_insight/reasoning/queue.py`

## Audit Trail

- EXTRACTED: 85 (97%)
- INFERRED: 3 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*