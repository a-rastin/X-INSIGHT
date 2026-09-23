# Reasoning Coordinator 2

> 6 nodes · cohesion 0.40

## Key Concepts

- **_enqueue_next_ready()** (6 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_has_pending_clarification()** (5 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **_read_applicability()** (5 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **Return persisted gate status, defaulting to ready (pre-gate rows).** (1 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **True when any question needs clarification and has no success yet. A…** (1 connections) — `backend/src/x_insight/reasoning/coordinator.py`
- **Enqueue the next ready question for one run (S46 slices 1-2). Next means the…** (1 connections) — `backend/src/x_insight/reasoning/coordinator.py`

## Relationships

- [Reasoning Coordinator Provider](Reasoning_Coordinator_Provider.md) (6 shared connections)
- [Reasoning Queue Proposal](Reasoning_Queue_Proposal.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/reasoning/coordinator.py`

## Audit Trail

- EXTRACTED: 13 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*