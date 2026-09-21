"""Injectable clock for identity (throttling windows; sessions have no timeout).

Production returns monotonic seconds. Tests monkeypatch ``now`` to advance a
controlled clock; session validity never consults it (NFR-02: no timeout).
"""

from __future__ import annotations

import time

_now_fn = time.monotonic


def now() -> float:
    """Return current clock seconds (monkeypatchable in tests)."""
    return _now_fn()


def set_now_fn(fn) -> None:  # type: ignore[no-untyped-def]
    """Override the clock (tests only)."""
    global _now_fn
    _now_fn = fn


def reset_now_fn() -> None:
    """Restore the production clock."""
    global _now_fn
    _now_fn = time.monotonic
