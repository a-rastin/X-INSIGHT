"""Shared retry budget and backoff (S47 slice 1).

One budget for the whole question job: ``MAX_ATTEMPTS`` total provider
POSTs (one POST per attempt, no nested adapter retries). Pure helpers so
the worker stays thin; no sleeping here — the queue persists the next
eligibility instant via ``available_at``.
"""

from __future__ import annotations

from typing import Any

MAX_ATTEMPTS = 3
MAX_DELAY_SECONDS = 60.0
BASE_DELAY_SECONDS = 2.0


def _provider_leaf(exc: BaseException) -> BaseException | None:
    """Return the driving ProviderError, unwrapping transport wrappers.

    The real MCP stdio transport runs estimation inside a task group, so
    a retryable :class:`ProviderError` arrives wrapped in an
    ``ExceptionGroup``. Only a leaf whose type is ``ProviderError``
    counts (matched by type name to keep this module pure and avoid
    import cycles); ``CoordinatorError`` and any other leaf fail fast.
    """
    if type(exc).__name__ == "ProviderError":
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _provider_leaf(sub)
            if found is not None:
                return found
    return None


def retryable_error(exc: BaseException) -> BaseException | None:
    """Return the retry-driving ProviderError, or None to fail fast."""
    leaf = _provider_leaf(exc)
    if leaf is not None and bool(getattr(leaf, "retryable", False) is True):
        return leaf
    return None


def is_retryable(exc: BaseException) -> bool:
    """Return True only for retryable provider failures.

    Source of truth is ``ProviderError.retryable`` (True for
    timeout/transient/rate_limited/invalid_cpt), read off the driving
    leaf even when the MCP transport wrapped it in an ``ExceptionGroup``.
    ``CoordinatorError`` and any non-``ProviderError`` lack the flag and
    fail fast.
    """
    return retryable_error(exc) is not None


def budget_exhausted(attempt_index: int | None) -> bool:
    """True when the shared budget is spent (attempt count reached max)."""
    return batch_exhausted(attempt_index, 0)


def batch_exhausted(attempt_count: int | None, batch_start: int | None = 0) -> bool:
    """True when the current batch budget is spent.

    Each manual retry starts a new bounded batch: only attempts since
    ``batch_start`` count against ``MAX_ATTEMPTS``. The attempt ledger
    stays monotonic (rows are never deleted); the batch window is
    ``attempt_count - batch_start >= MAX_ATTEMPTS``.
    """
    if attempt_count is None:
        return True
    try:
        count = int(attempt_count)
        start = int(batch_start or 0)
    except (TypeError, ValueError):
        return True
    return (count - start) >= MAX_ATTEMPTS


def backoff_delay_seconds(attempt_index: int, retry_after: Any = None) -> float:
    """Deterministic backoff delay in seconds, capped at 60s.

    Exponential ``base 2s * 2**(attempt-1)`` plus a small deterministic
    bounded jitter (< 1s, function of the attempt index only — no random,
    no wall clock). When a ``Retry-After`` value is present it wins,
    capped with ``min(retry_after, 60)``.
    """
    if retry_after is not None:
        try:
            parsed = float(retry_after)
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None and parsed == parsed and parsed >= 0:
            return min(parsed, MAX_DELAY_SECONDS)
    attempt = int(attempt_index)
    if attempt < 1:
        attempt = 1
    base = BASE_DELAY_SECONDS * (2.0 ** (attempt - 1))
    jitter = (attempt * 0.37) % 1.0
    return min(base + jitter, MAX_DELAY_SECONDS)
