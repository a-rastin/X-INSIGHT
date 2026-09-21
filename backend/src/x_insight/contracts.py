"""Shared HTTP/JSON contracts.

Canonical JSON and UTC helpers are documented at their actual public uses:
``canonical_json``/``content_hash`` back future fingerprint/snapshot hashing
(plan sections 4.2/8.1); ``utc_now``/``to_utc_z`` back server timestamps in
error bodies, readiness, and later audit/signed records. Error envelope shape
matches plan section 4.3. Revision (``If-Match``/ETag) and ``Idempotency-Key``
parsers are the single convention later command routes use.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

MAX_BODY_BYTES = 1024 * 1024


def new_request_id() -> str:
    """Return a new random request correlation ID (UUID text)."""
    return str(uuid.uuid4())


def error_body(
    code: str,
    message: str,
    request_id: str,
    field_errors: dict[str, str] | None = None,
    retryable: bool = False,
) -> dict[str, Any]:
    """Build the standard error envelope (plan section 4.3)."""
    return {
        "code": code,
        "message": message,
        "field_errors": field_errors or {},
        "request_id": request_id,
        "retryable": retryable,
    }


def canonical_json(value: Any) -> bytes:
    """Encode canonical UTF-8 JSON: sorted keys, compact, finite numbers.

    Object keys sort; arrays keep semantic order; ``allow_nan=False`` rejects
    non-finite floats instead of hashing ``NaN``/``Infinity``.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    """SHA-256 hex of the canonical JSON encoding."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time (server timestamps)."""
    return datetime.now(UTC)


def to_utc_z(value: datetime) -> str:
    """Serialize a datetime as UTC ``...Z`` ISO-8601 text."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_if_match(headers: Mapping[str, str]) -> str | None:
    """Return the ``If-Match`` revision tag, or None when absent."""
    raw = headers.get("if-match") or headers.get("If-Match")
    if raw is None:
        return None
    tag = raw.strip().strip('"').strip()
    return tag or None


def parse_idempotency_key(headers: Mapping[str, str]) -> str | None:
    """Return the ``Idempotency-Key`` value, or None when absent/invalid."""
    raw = headers.get("idempotency-key") or headers.get("Idempotency-Key")
    if raw is None:
        return None
    key = raw.strip()
    if not key or len(key) > 128:
        return None
    return key
