"""S58 item 4: bounded LRU for immutable parsed definitions/catalogs (T8).

Scope (tasks.md S58.4; plan.md section 11): in-process bounded memory for
immutable parsed artifacts only (network definitions, controlled
terminology/catalogs), keyed by content hash. ``MAX_ENTRIES`` bounds memory;
overflow evicts the least-recently-used entry, which re-parses on next use.

Patient prohibition (binding): patient CPTs/projections must NEVER use this
cache. Per-run/per-patient artifacts are scoped by run/question only, never
by a base-model key, and never reused across patients. Callers MUST build
the cache key from the immutable bytes alone (``sha256`` of the bytes plus
a schema/catalog version, e.g. ``f"ddi-terminology:{VERSION}:{digest}"``)
and MUST NOT mix patient, run, encounter, or question-instance identifiers
into the key or the cached value. This module stores opaque ``(key, value)``
pairs and cannot inspect key semantics; the key contract is enforced by the
call sites, each of which reads immutable release/catalog bytes only.

No broker, no redis, no database table is added: plan.md section 11
forbids new caching infrastructure without measured evidence. This is a
plain in-process ``OrderedDict`` LRU guarded by a lock.
"""

from __future__ import annotations

import sys
import threading
from collections import OrderedDict
from collections.abc import Callable
from types import ModuleType
from typing import Any, TypeVar

MAX_ENTRIES: int = 128

T = TypeVar("T")

_store: OrderedDict[str, Any] = OrderedDict()
_guard = threading.Lock()


def get_or_parse(key: str, raw: bytes, parse: Callable[[bytes], T]) -> T:
    """Return the cached parse for ``key``, parsing ``raw`` once on a miss.

    ``key`` MUST be a non-empty string derived from the immutable content
    (content hash plus artifact/schema version). ``raw`` is the exact
    immutable bytes; ``parse`` is a pure function of those bytes. Hits
    refresh LRU recency without re-parsing. Misses parse, store under
    ``key``, evict least-recently-used entries past ``MAX_ENTRIES``, and
    return the fresh value. Parse failures propagate and are never cached.
    """
    if not isinstance(key, str) or not key:
        raise ValueError("cache key must be a non-empty string")
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("raw must be bytes")
    with _guard:
        if key in _store:
            _store.move_to_end(key)
            return _store[key]  # type: ignore[no-any-return]
    parsed = parse(bytes(raw))
    with _guard:
        if key in _store:
            _store.move_to_end(key)
            return _store[key]  # type: ignore[no-any-return]
        _store[key] = parsed
        _store.move_to_end(key)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)
        return parsed


def clear() -> None:
    """Empty the cache (tests and restore-path hygiene only)."""
    with _guard:
        _store.clear()


class _DefinitionCacheModule(ModuleType):
    """Module type exposing ``len(module)`` as the live entry count."""

    def __len__(self) -> int:
        with _guard:
            return len(_store)


sys.modules[__name__].__class__ = _DefinitionCacheModule
