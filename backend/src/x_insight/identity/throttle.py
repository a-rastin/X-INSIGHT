"""In-process login throttling (prototype-basic; per-process memory).

Rules: at most 5 failures per (username, IP) per 60s; the 6th is 429.
Success clears the key. Uses the injectable identity clock.
"""

# ponytail: process-local dict; shared DB counter if contention is measured.

from __future__ import annotations

from x_insight.identity import clock

MAX_FAILURES = 5
WINDOW_SECONDS = 60.0

_attempts: dict[str, list[float]] = {}


def _prune(key: str, at: float) -> list[float]:
    kept = [t for t in _attempts.get(key, []) if at - t < WINDOW_SECONDS]
    _attempts[key] = kept
    return kept


def throttled(key: str) -> bool:
    """Return True when the key exhausted its failure budget."""
    return len(_prune(key, clock.now())) >= MAX_FAILURES


def record_failure(key: str) -> None:
    """Record one failed login for the key."""
    seen = _prune(key, clock.now())
    seen.append(clock.now())
    _attempts[key] = seen


def clear(key: str) -> None:
    """Clear failures after a successful login (or test reset)."""
    _attempts.pop(key, None)


def reset_all() -> None:
    """Clear all throttle state (tests only)."""
    _attempts.clear()
