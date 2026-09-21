# throttle.py

> 19 nodes

## Key Concepts

- **throttle.py** (13 connections) — `backend/src/x_insight/identity/throttle.py`
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

- [_require_session](_require_session.md) (3 shared connections)
- [test_drafts.py](test_drafts.py.md) (3 shared connections)
- [routes.py](routes.py.md) (2 shared connections)
- [test_content.py](test_content.py.md) (1 shared connections)
- [test_identity.py](test_identity.py.md) (1 shared connections)
- [evaluation.py](evaluation.py.md) (1 shared connections)

## Source Files

- `backend/src/x_insight/identity/__init__.py`
- `backend/src/x_insight/identity/clock.py`
- `backend/src/x_insight/identity/throttle.py`

## Audit Trail

- EXTRACTED: 33 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*