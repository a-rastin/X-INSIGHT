"""S43 slice 3: bounded provider CPT estimation with tool bridging."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from x_insight.models.inference import validate_cpt_response
from x_insight.reasoning.provider_config import validate_url_for_request

TOOL_NAME = "get_question_patient_inputs"
MAX_TOOL_CALLS = 10
REQUEST_TIMEOUT_S = 60
MAX_REQUEST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 512 * 1024

_REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)

_ALLOWED_BODY_KEYS = (
    "prompt",
    "network_contract",
    "cpt_contract",
    "projection",
    "projection_hash",
    "tools",
    "tool_results",
    "messages",
)


class ProviderError(Exception):
    """Provider failure with machine-readable code and retry hint."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _payload_from_bridge_result(res: Any) -> Any:
    if isinstance(res, dict) and "result" in res:
        return res["result"]
    if isinstance(res, dict) and "projection" in res:
        return res["projection"]
    raise ProviderError("invalid_cpt", "Bridge returned an unexpected shape.", True)


def _reject_ambiguous(data: dict[str, Any]) -> None:
    if "tables" in data and "choices" in data:
        raise ProviderError("ambiguous", "Provider returned multiple finals.", False)
    choices = data.get("choices")
    if isinstance(choices, list) and len(choices) > 1:
        raise ProviderError("ambiguous", "Provider returned multiple finals.", False)
    if isinstance(choices, list) and len(choices) == 1:
        only = choices[0]
        if isinstance(only, dict) and "message" not in only and "tables" in only:
            raise ProviderError(
                "ambiguous", "Provider returned multiple finals.", False
            )


def _request_size_bytes(body: dict[str, Any]) -> int:
    return len(json.dumps(body, sort_keys=True, default=str).encode("utf-8"))


def _check_request_size(body: dict[str, Any]) -> None:
    if _request_size_bytes(body) > MAX_REQUEST_BYTES:
        raise ProviderError("oversized", "Provider request exceeded size bound.", False)


def _post_once(url: str, api_key: str, body: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    }
    try:
        with httpx.Client(follow_redirects=False, timeout=_REQUEST_TIMEOUT) as client:
            response = client.post(url, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        raise ProviderError(
            "timeout",
            f"Provider request timed out: {type(exc).__name__}.",
            True,
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            "transport", f"Provider request failed: {type(exc).__name__}.", False
        ) from exc
    status = response.status_code
    if status != 200:
        if status in (401, 403):
            raise ProviderError(
                "auth_failed", f"Provider returned status {status}.", False
            )
        if status == 404:
            raise ProviderError(
                "model_not_found", f"Provider returned status {status}.", False
            )
        if status == 429:
            raise ProviderError(
                "rate_limited", f"Provider returned status {status}.", True
            )
        if status == 422:
            raise ProviderError(
                "capability_unsupported",
                f"Provider returned status {status}.",
                False,
            )
        if status in (500, 502, 503, 504):
            raise ProviderError(
                "transient", f"Provider returned status {status}.", True
            )
        raise ProviderError("bad_status", f"Provider returned status {status}.", False)
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ProviderError(
            "oversized", "Provider response exceeded size bound.", False
        )
    try:
        data: Any = response.json()
    except ValueError as exc:
        raise ProviderError(
            "invalid_cpt", "Provider response was not JSON.", True
        ) from exc
    if not isinstance(data, dict):
        raise ProviderError("invalid_cpt", "Provider response was not an object.", True)
    return data


def _validated_tool_calls(data: dict[str, Any]) -> list[dict[str, Any]]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("invalid_cpt", "Provider response had no choices.", True)
    first = choices[0]
    if not isinstance(first, dict):
        raise ProviderError("invalid_cpt", "Provider choice was malformed.", True)
    message = first.get("message")
    if not isinstance(message, dict):
        raise ProviderError("invalid_cpt", "Provider message was malformed.", True)
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        raise ProviderError(
            "invalid_cpt", "Provider response had neither tables nor tool calls.", True
        )
    for call in tool_calls:
        if not isinstance(call, dict):
            raise ProviderError("tool_rejected", "Disallowed tool call.", False)
        cid = call.get("id")
        if not isinstance(cid, str) or not cid:
            raise ProviderError("tool_rejected", "Disallowed tool call.", False)
        fn = call.get("function")
        if not isinstance(fn, dict):
            raise ProviderError("tool_rejected", "Disallowed tool call.", False)
        if fn.get("name") != TOOL_NAME:
            raise ProviderError("tool_rejected", "Disallowed tool call.", False)
        args_raw = fn.get("arguments")
        try:
            if isinstance(args_raw, str):
                parsed: Any = json.loads(args_raw)
            elif isinstance(args_raw, dict):
                parsed = args_raw
            else:
                raise ProviderError("tool_rejected", "Disallowed tool call.", False)
        except (ValueError, TypeError) as exc:
            raise ProviderError(
                "tool_rejected", "Disallowed tool call.", False
            ) from exc
        if parsed != {}:
            raise ProviderError("tool_rejected", "Disallowed tool call.", False)
    return tool_calls


def estimate_cpts(
    request: dict[str, Any],
    permitted_tool_bridge: Callable[[str, dict[str, Any], str], dict[str, Any]],
) -> dict[str, Any]:
    """Estimate CPTs with an initial MCP read and one tool-call loop."""
    raw_url = request.get("base_url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ProviderError("invalid_request", "base_url must be a string", False)
    url = validate_url_for_request(raw_url)
    api_key = request.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        raise ProviderError("invalid_request", "api_key must be a string", False)
    body: dict[str, Any] = {}
    for key in _ALLOWED_BODY_KEYS:
        if key in request:
            body[key] = request[key]
    if request.get("capability_mode") == "schema":
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "cpt_response",
                "strict": True,
                "schema": {"type": "object"},
            },
        }

    _check_request_size(body)
    data = _post_once(url, api_key, body)

    _reject_ambiguous(data)

    if "tables" in data:
        # Initial MCP read (after the single POST for the direct path).
        # Propagates grant_denied without an extra POST.
        init_res = permitted_tool_bridge(TOOL_NAME, {}, "initial")
        _payload_from_bridge_result(init_res)
        try:
            return validate_cpt_response(data)
        except ValueError as exc:
            raise ProviderError("invalid_cpt", str(exc), True) from exc

    if "choices" not in data:
        raise ProviderError("invalid_cpt", "Provider response was not usable.", True)

    total_calls = 0
    current_body = body
    current_data = data
    initial_done = False

    while True:
        _reject_ambiguous(current_data)
        if "tables" in current_data:
            try:
                return validate_cpt_response(current_data)
            except ValueError as exc:
                raise ProviderError("invalid_cpt", str(exc), True) from exc
        tool_calls = _validated_tool_calls(current_data)
        if total_calls + len(tool_calls) > MAX_TOOL_CALLS:
            raise ProviderError("budget_exceeded", "Too many tool calls.", False)
        if not initial_done:
            init_res = permitted_tool_bridge(TOOL_NAME, {}, "initial")
            initial_payload = _payload_from_bridge_result(init_res)
            current_body = dict(current_body)
            current_body["projection"] = initial_payload
            initial_done = True
        tool_results: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = [
            {"role": "assistant", "tool_calls": tool_calls}
        ]
        for call in tool_calls:
            cid_any = call.get("id")
            assert isinstance(cid_any, str)
            cid: str = cid_any
            tres = permitted_tool_bridge(TOOL_NAME, {}, cid)
            payload = _payload_from_bridge_result(tres)
            tool_results.append({"call_id": cid, "result": payload})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": cid,
                    "content": json.dumps(payload, sort_keys=True, default=str),
                }
            )
            total_calls += 1
        next_body = dict(current_body)
        next_body["tool_results"] = tool_results
        next_body["messages"] = messages
        _check_request_size(next_body)
        current_data = _post_once(url, api_key, next_body)
        current_body = next_body
