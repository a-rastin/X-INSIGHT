"""Provider configuration crypto, destination allowlist, capability adapter.

S42 is the only permanent provider client path: saving settings never calls
the adapter; only the explicit test endpoint does, exactly once per call.
All secrets in this module stay in memory or in the Fernet ciphertext column;
diagnostics, logs and audit details never carry the key.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import logging
import os
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENCRYPTION_ENV_VARS = (
    "X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY",
    "PROVIDER_ENCRYPTION_KEY",
)
ALLOW_LOCAL_ENV_VAR = "X_INSIGHT_PROVIDER_ALLOW_LOCAL"

PLACEHOLDER_KEY = "****"
TOOL_NAME = "get_question_patient_inputs"

ADAPTER_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
MAX_REDIRECT_HOPS = 3
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

_FALLBACK_KEY_MATERIAL = b"x-insight-dev-only-provider-key-fallback"
_fallback_warned = False


class ProviderURLBlocked(ValueError):
    """A provider destination failed the allowlist; routes map this to 422."""


def _deployment_key() -> bytes:
    """Return the Fernet key bytes, deriving from env text when needed."""
    global _fallback_warned
    for env_var in ENCRYPTION_ENV_VARS:
        raw = os.environ.get(env_var, "").strip()
        if not raw:
            continue
        candidate = raw.encode("utf-8")
        try:
            Fernet(candidate)
        except Exception:
            # Accept an arbitrary operator passphrase by deriving a key.
            return base64.urlsafe_b64encode(hashlib.sha256(candidate).digest())
        return candidate
    if not _fallback_warned:
        logger.warning(
            "Provider key encryption uses a dev-only deterministic fallback; "
            "set %s in deployment.",
            ENCRYPTION_ENV_VARS[0],
        )
        _fallback_warned = True
    return base64.urlsafe_b64encode(hashlib.sha256(_FALLBACK_KEY_MATERIAL).digest())


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt one API key with the deployment-held key (never logged)."""
    return Fernet(_deployment_key()).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_api_key(ciphertext: str) -> str:
    """Decrypt a stored API key; raises on tampering or key rotation."""
    try:
        token = Fernet(_deployment_key()).decrypt(ciphertext.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Stored provider key cannot be decrypted.") from exc
    return token.decode("utf-8")


def allow_local_enabled() -> bool:
    """Read the operator local-endpoint flag per request, not at import."""
    return os.environ.get(ALLOW_LOCAL_ENV_VAR, "").strip().lower() == "true"


def _host_is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_literal(host: str, *, allow_local: bool) -> None:
    """Reject non-global IP literals (loopback only when explicitly allowed)."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return
    if addr.is_loopback:
        if allow_local:
            return
        raise ProviderURLBlocked(
            "Loopback provider endpoints require "
            f"{ALLOW_LOCAL_ENV_VAR}=true explicitly set by the operator."
        )
    if not addr.is_global:
        raise ProviderURLBlocked(f"Provider host {host!r} is not publicly routable.")


def _check_hostname(host: str, *, scheme: str) -> None:
    lowered = host.lower().rstrip(".")
    if lowered in {"metadata.google.internal", "metadata"} or lowered.endswith(
        ".metadata.google.internal"
    ):
        raise ProviderURLBlocked("Cloud metadata endpoints are never allowed.")
    if scheme == "http" and not _host_is_loopback(host):
        raise ProviderURLBlocked("Plain http is only allowed for local endpoints.")


def _split_url(raw: str) -> tuple[str, str, int]:
    parsed = urlparse(raw.strip())
    if parsed.scheme not in ("http", "https"):
        raise ProviderURLBlocked(
            f"Provider scheme {parsed.scheme!r} is not allowed; use https."
        )
    host = parsed.hostname or ""
    if not host:
        raise ProviderURLBlocked("Provider URL must include a host.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, host, port


def validate_url_for_save(raw: str) -> str:
    """Syntactic allowlist for saving: scheme, metadata and literal checks."""
    scheme, host, _ = _split_url(raw)
    _check_hostname(host, scheme=scheme)
    _check_literal(host, allow_local=allow_local_enabled())
    return raw.strip()


def validate_url_for_request(raw: str) -> str:
    """Full allowlist before any outbound byte: save checks plus DNS."""
    scheme, host, port = _split_url(raw)
    _check_hostname(host, scheme=scheme)
    allow_local = allow_local_enabled()
    _check_literal(host, allow_local=allow_local)
    hostname_loopback = _host_is_loopback(host)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ProviderURLBlocked(f"Provider host {host!r} cannot be resolved.") from exc
    if not infos:
        raise ProviderURLBlocked(f"Provider host {host!r} cannot be resolved.")
    for info in infos:
        sockaddr = info[4]
        try:
            addr = ipaddress.ip_address(str(sockaddr[0]))
        except ValueError as exc:
            raise ProviderURLBlocked(
                f"Provider host {host!r} resolved to an invalid address."
            ) from exc
        if addr.is_loopback:
            if hostname_loopback and allow_local:
                continue
            raise ProviderURLBlocked(
                f"Provider host {host!r} resolves to a loopback address."
            )
        if not addr.is_global:
            raise ProviderURLBlocked(
                f"Provider host {host!r} resolves to a non-public address."
            )
    return raw.strip()


def _synthetic_payload(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": json.dumps({"synthetic": "capability-probe"}),
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        "tool_choice": "auto",
    }


def _interpret(
    response: httpx.Response, model: str, request_count: int
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "credential_ok": False,
        "model_ok": False,
        "tool_ok": False,
        "json_ok": False,
        "diagnostic": "",
        "request_count": request_count,
    }
    if response.status_code in (401, 403):
        return {
            **base,
            "diagnostic": (
                f"Provider rejected the credentials (status {response.status_code})."
            ),
        }
    if response.status_code != 200:
        return {
            **base,
            "diagnostic": (f"Provider returned status {response.status_code}."),
        }
    try:
        data = response.json()
    except ValueError:
        return {**base, "diagnostic": "Provider response was not JSON."}
    if not isinstance(data, dict):
        return {**base, "diagnostic": "Provider response was not an object."}
    choices = data.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message", {}) if isinstance(first, dict) else {}
    if not isinstance(message, dict):
        message = {}
    content = message.get("content")
    json_ok = False
    if isinstance(content, str):
        try:
            json.loads(content)
        except ValueError:
            json_ok = False
        else:
            json_ok = True
    tool_calls = message.get("tool_calls") or []
    tool_ok = (
        isinstance(tool_calls, list)
        and len(tool_calls) > 0
        and all(
            isinstance(call, dict)
            and call.get("id")
            and isinstance(call.get("function"), dict)
            and call["function"].get("name")
            for call in tool_calls
        )
    )
    reported_model = data.get("model")
    model_ok = (reported_model == model) if isinstance(reported_model, str) else True
    missing = [
        name
        for name, ok in (
            ("credential", True),
            ("model", model_ok),
            ("tool", tool_ok),
            ("json", json_ok),
        )
        if not ok
    ]
    return {
        **base,
        "credential_ok": True,
        "model_ok": model_ok,
        "tool_ok": tool_ok,
        "json_ok": json_ok,
        "diagnostic": (
            "Provider capabilities verified."
            if not missing
            else f"Capability shortfall: {', '.join(missing)}."
        ),
    }


def check_capabilities(
    base_url: str, api_key: str | None, model: str
) -> dict[str, Any]:
    """Run one synthetic OpenAI-compatible capability exchange.

    ``base_url`` is the full chat-completions endpoint URL (the S42 synthetic
    probe treats it as such); redirects are followed manually up to
    ``MAX_REDIRECT_HOPS`` with every hop re-validated. Transport failures
    return failed flags; only allowlist violations raise
    :class:`ProviderURLBlocked`. The key travels in the Authorization header
    only and never appears in the returned diagnostic.
    """
    url = validate_url_for_request(base_url)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    payload = _synthetic_payload(model)
    request_count = 0
    try:
        with httpx.Client(follow_redirects=False, timeout=ADAPTER_TIMEOUT) as client:
            for _ in range(MAX_REDIRECT_HOPS + 1):
                response = client.post(url, json=payload, headers=headers)
                request_count += 1
                location = response.headers.get("location")
                if response.status_code in REDIRECT_STATUSES and location:
                    url = validate_url_for_request(urljoin(url, location))
                    continue
                return _interpret(response, model, request_count)
    except httpx.HTTPError as exc:
        return {
            "credential_ok": False,
            "model_ok": False,
            "tool_ok": False,
            "json_ok": False,
            "diagnostic": f"Provider request failed: {type(exc).__name__}.",
            "request_count": request_count,
        }
    raise ProviderURLBlocked("Provider redirected too many times.")
