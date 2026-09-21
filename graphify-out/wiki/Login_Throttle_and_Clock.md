# Login Throttle and Clock

> 19 nodes · cohesion 0.13

## Key Concepts

- **throttle.py** (15 connections) — `backend/src/x_insight/identity/throttle.py`
- **clock.py** (6 connections) — `backend/src/x_insight/identity/clock.py`
- **record_failure()** (5 connections) — `backend/src/x_insight/identity/throttle.py`
- **throttled()** (5 connections) — `backend/src/x_insight/identity/throttle.py`
- **now()** (4 connections) — `backend/src/x_insight/identity/clock.py`
- **clear()** (3 connections) — `backend/src/x_insight/identity/throttle.py`
- **_prune()** (3 connections) — `backend/src/x_insight/identity/throttle.py`
- **reset_now_fn()** (2 connections) — `backend/src/x_insight/identity/clock.py`
- **set_now_fn()** (2 connections) — `backend/src/x_insight/identity/clock.py`
- **identity/__init__.py** (2 connections) — `backend/src/x_insight/identity/__init__.py`
- **time** (2 connections)
- **Injectable clock for identity (throttling windows; sessions have no timeout).…** (1 connections) — `backend/src/x_insight/identity/clock.py`
- **Return current clock seconds (monkeypatchable in tests).** (1 connections) — `backend/src/x_insight/identity/clock.py`
- **Override the clock (tests only).** (1 connections) — `backend/src/x_insight/identity/clock.py`
- **Restore the production clock.** (1 connections) — `backend/src/x_insight/identity/clock.py`
- **In-process login throttling (prototype-basic; per-process memory). Rules: at…** (1 connections) — `backend/src/x_insight/identity/throttle.py`
- **Return True when the key exhausted its failure budget.** (1 connections) — `backend/src/x_insight/identity/throttle.py`
- **Record one failed login for the key.** (1 connections) — `backend/src/x_insight/identity/throttle.py`
- **Clear failures after a successful login (or test reset).** (1 connections) — `backend/src/x_insight/identity/throttle.py`

## Relationships

- [Identity Login and Sessions](Identity_Login_and_Sessions.md) (5 shared connections)
- [C-SSRS HTTP Tests](C-SSRS_HTTP_Tests.md) (1 shared connections)
- [Diagnosis Evaluation Tests](Diagnosis_Evaluation_Tests.md) (1 shared connections)
- [Draft Lifecycle Tests](Draft_Lifecycle_Tests.md) (1 shared connections)
- [History HTTP Tests](History_HTTP_Tests.md) (1 shared connections)
- [Assessment Engine and PANSS Tests](Assessment_Engine_and_PANSS_Tests.md) (1 shared connections)
- [Patient Registration Tests](Patient_Registration_Tests.md) (1 shared connections)
- [Test Fixture Resets](Test_Fixture_Resets.md) (1 shared connections)
- [MCP Evaluation Harness](MCP_Evaluation_Harness.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/__init__.py`
- `backend/src/x_insight/identity/clock.py`
- `backend/src/x_insight/identity/throttle.py`

## Audit Trail

- EXTRACTED: 35 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*