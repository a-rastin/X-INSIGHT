# Identity Throttle Clock

> 19 nodes · cohesion 0.13

## Key Concepts

- **throttle.py** (15 connections) — `backend/src/x_insight/identity/throttle.py`
- **clock.py** (6 connections) — `backend/src/x_insight/identity/clock.py`
- **record_failure()** (5 connections) — `backend/src/x_insight/identity/throttle.py`
- **throttled()** (5 connections) — `backend/src/x_insight/identity/throttle.py`
- **now()** (4 connections) — `backend/src/x_insight/identity/clock.py`
- **clear()** (3 connections) — `backend/src/x_insight/identity/throttle.py`
- **_prune()** (3 connections) — `backend/src/x_insight/identity/throttle.py`
- **time** (3 connections)
- **reset_now_fn()** (2 connections) — `backend/src/x_insight/identity/clock.py`
- **set_now_fn()** (2 connections) — `backend/src/x_insight/identity/clock.py`
- **identity/__init__.py** (2 connections) — `backend/src/x_insight/identity/__init__.py`
- **Injectable clock for identity (throttling windows; sessions have no timeout).…** (1 connections) — `backend/src/x_insight/identity/clock.py`
- **Return current clock seconds (monkeypatchable in tests).** (1 connections) — `backend/src/x_insight/identity/clock.py`
- **Override the clock (tests only).** (1 connections) — `backend/src/x_insight/identity/clock.py`
- **Restore the production clock.** (1 connections) — `backend/src/x_insight/identity/clock.py`
- **In-process login throttling (prototype-basic; per-process memory). Rules: at…** (1 connections) — `backend/src/x_insight/identity/throttle.py`
- **Return True when the key exhausted its failure budget.** (1 connections) — `backend/src/x_insight/identity/throttle.py`
- **Record one failed login for the key.** (1 connections) — `backend/src/x_insight/identity/throttle.py`
- **Clear failures after a successful login (or test reset).** (1 connections) — `backend/src/x_insight/identity/throttle.py`

## Relationships

- [Identity Hashing](Identity_Hashing.md) (5 shared connections)
- [HTTP C-SSRS Tests](HTTP_C-SSRS_Tests.md) (1 shared connections)
- [HTTP Diagnosis Tests](HTTP_Diagnosis_Tests.md) (1 shared connections)
- [HTTP Drafts Tests](HTTP_Drafts_Tests.md) (1 shared connections)
- [MCP Server](MCP_Server.md) (1 shared connections)
- [Assessment PANSS Tests](Assessment_PANSS_Tests.md) (1 shared connections)
- [HTTP Patients Tests](HTTP_Patients_Tests.md) (1 shared connections)
- [Identity Throttle C-SSRS](Identity_Throttle_C-SSRS.md) (1 shared connections)
- [MCP Builder Evaluation 4](MCP_Builder_Evaluation_4.md) (1 shared connections)
- [Provider Estimation Tests Init](Provider_Estimation_Tests_Init.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/__init__.py`
- `backend/src/x_insight/identity/clock.py`
- `backend/src/x_insight/identity/throttle.py`

## Audit Trail

- EXTRACTED: 36 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*