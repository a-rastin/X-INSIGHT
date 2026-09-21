"""Standard password hashing (stdlib PBKDF2-HMAC-SHA256).

No new dependency: hashlib/secrets/hmac are stdlib. Parameters follow the
OWASP PBKDF2 guidance selected at implementation time (600k SHA-256
iterations); changing them is a versioned config decision, not a silent
tweak. Passwords are never trimmed or normalized here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ITERATIONS = 600_000
SALT_BYTES = 16
DKLEN = 32
_PREFIX = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """Hash an exact (untrimmed) password; caller rejects empty input."""
    salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return (
        f"{_PREFIX}${ITERATIONS}"
        f"${base64.b64encode(salt).decode()}"
        f"${base64.b64encode(dk).decode()}"
    )


def verify_password(password: str, stored: str) -> bool:
    """Compare an exact password against a stored hash; False on malformed."""
    try:
        prefix, iter_s, salt_b64, hash_b64 = stored.split("$")
        if prefix != _PREFIX:
            return False
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
    except Exception:
        return False
    try:
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
    except Exception:
        return False
    return hmac.compare_digest(candidate, expected)
