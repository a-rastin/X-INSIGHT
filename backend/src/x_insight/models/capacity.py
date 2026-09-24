"""S58 item 2: model-capacity bench harness (T5).

Synthetic fixtures only; never BNs/ as oracle. Exact inference only via
:mod:`x_insight.models.inference` (pinned pgmpy 1.1.2, float64,
artifact-node-order through ``ENGINE_PIN``); never normalizes, clips,
truncates, or approximates.

Peak-RSS method: ``resource.getrusage(RUSAGE_SELF).ru_maxrss`` sampled
immediately before/after the exact-inference call; delta is
``max(0, after - before)`` in bytes (Linux ``ru_maxrss`` is kilobytes,
converted by 1024; other platforms use the raw value as bytes).
Precision limitation: kernel page granularity, process-wide peak (may be
zero when inference allocates below the existing peak, and includes
unrelated process activity between the two samples).
"""

from __future__ import annotations

import json
import math
import resource
import sys
import time
from typing import Any

from x_insight.models import inference, semantics, validation
from x_insight.models.inference import ENGINE_PIN

_ERROR_BOUND = 500


def _bound(text: str) -> str:
    return text[:_ERROR_BOUND]


def _peak_rss_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    peak = int(usage.ru_maxrss)
    if sys.platform.startswith("linux"):
        return peak * 1024
    return peak


def _canonical_bytes(response: dict[str, Any]) -> bytes:
    try:
        text = json.dumps(
            response, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(_bound(f"invalid CPT response: {exc}")) from exc
    return text.encode("utf-8")


def _effective_limits(limits: dict[str, Any] | None) -> dict[str, Any]:
    eff: dict[str, Any] = dict(semantics.DEFAULT_LIMITS)
    if isinstance(limits, dict):
        eff.update(limits)
    return eff


def _rejected(
    *,
    request_bytes: int,
    measurements: dict[str, Any],
    limits: dict[str, Any],
    diagnostics: list[str],
    error: str,
) -> dict[str, Any]:
    diags = sorted(str(d) for d in diagnostics)
    return {
        "request_bytes": int(request_bytes),
        "output_bytes": 0,
        "measurements": dict(measurements),
        "limits": dict(limits),
        "admitted": False,
        "diagnostics": diags,
        "failure_kind": "rejected",
        "error": _bound(error),
    }


def measure(
    network_xml: bytes,
    cpt_response: dict[str, Any],
    queries: list[dict[str, Any]],
    limits: dict[str, Any] | None,
    timeout_s: float,
) -> dict[str, Any]:
    """Bench one synthetic network: sizes, exact inference, admission.

    On admission rejection returns a ``rejected`` report (no posterior,
    no inference executed). On impossible evidence or timeout raises a
    bounded ``ValueError`` (never approximates).
    """
    try:
        timeout = float(timeout_s)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            _bound(f"resource exhausted: invalid timeout_s ({exc})")
        ) from exc
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError(
            _bound(f"resource exhausted: timeout_s {timeout_s!r} limit exhausted")
        )
    if not isinstance(network_xml, (bytes, bytearray)):
        raise ValueError(_bound("network_xml must be bytes"))
    if not isinstance(cpt_response, dict):
        raise ValueError(_bound("cpt_response must be a dict"))
    if not isinstance(queries, list) or not queries:
        raise ValueError(_bound("queries must be a non-empty list"))

    raw_request = _canonical_bytes(cpt_response)
    raw_request_bytes = len(raw_request)

    try:
        accepted = inference.validate_cpt_response(cpt_response)
    except ValueError as exc:
        raise ValueError(_bound(str(exc))) from exc

    try:
        validated = validation.validate_xmlbif(bytes(network_xml))
    except Exception as exc:
        eff = _effective_limits(limits if isinstance(limits, dict) else None)
        diag = sorted(
            [
                f"request_bytes={raw_request_bytes}",
                f"xml_bytes={len(bytes(network_xml))}",
                f"validation_error={str(exc)[:200]}",
            ]
        )
        return _rejected(
            request_bytes=raw_request_bytes,
            measurements={
                "xml_bytes": len(bytes(network_xml)),
                "node_count": 0,
                "cpt_cells": 0,
                "request_bytes": raw_request_bytes,
                "output_bytes": 0,
            },
            limits=eff,
            diagnostics=diag,
            error=f"rejected: {exc}",
        )

    admission = semantics.check_admission(
        validated, limits if isinstance(limits, dict) else None
    )
    adm_measurements = admission.get("measurements", {})
    adm_limits = admission.get("limits", _effective_limits(None))
    adm_diagnostics = admission.get("diagnostics", [])
    if admission.get("admitted") is not True:
        errors = admission.get("errors", [])
        detail = "; ".join(
            str(e.get("message", e.get("code", ""))) if isinstance(e, dict) else str(e)
            for e in errors
            if isinstance(e, (dict, str))
        )
        base_diags = (
            [str(d) for d in adm_diagnostics]
            if isinstance(adm_diagnostics, list)
            else []
        )
        extra = [f"request_bytes={raw_request_bytes}"]
        diagnostics = sorted(base_diags + extra)
        xml_bytes = adm_measurements.get("xml_bytes", len(bytes(network_xml)))
        node_count = adm_measurements.get("node_count", 0)
        cpt_cells = adm_measurements.get("cpt_cells", 0)
        err_text = f"rejected: {detail}" if detail else "rejected: over limit"
        return _rejected(
            request_bytes=raw_request_bytes,
            measurements={
                "xml_bytes": xml_bytes,
                "node_count": node_count,
                "cpt_cells": cpt_cells,
                "request_bytes": raw_request_bytes,
                "output_bytes": 0,
            },
            limits=dict(adm_limits) if isinstance(adm_limits, dict) else {},
            diagnostics=diagnostics,
            error=err_text,
        )

    source_sha = validated.get("source_sha256")
    if accepted.get("network_hash") != source_sha:
        # Synthetic bench fixtures use the placeholder "synthetic"; real
        # callers must supply the exact source hash (mismatch still fails).
        if accepted.get("network_hash") == "synthetic" and isinstance(source_sha, str):
            accepted["network_hash"] = source_sha
        else:
            raise ValueError(_bound("network_hash must equal validated source_sha256"))

    request_bytes_canonical = _canonical_bytes(accepted)
    request_bytes = len(request_bytes_canonical)

    try:
        artifact = inference.build_effective_artifact(validated, accepted)
    except ValueError as exc:
        raise ValueError(_bound(str(exc))) from exc

    effective_xml = artifact.get("effective_xml")
    if not isinstance(effective_xml, (bytes, bytearray)):
        raise ValueError(_bound("effective artifact missing effective_xml"))
    output_bytes = len(bytes(effective_xml))

    first = queries[0]
    if not isinstance(first, dict):
        raise ValueError(_bound("query must be a dict"))
    target = first.get("target")
    state = first.get("state")
    evidence = first.get("evidence", {})
    if not isinstance(target, str) or not isinstance(state, str):
        raise ValueError(_bound("query target/state must be strings"))
    if not isinstance(evidence, dict):
        raise ValueError(_bound("query evidence must be a dict"))
    norm_evidence: dict[str, str] = {}
    for k, v in evidence.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValueError(_bound("query evidence keys/values must be strings"))
        norm_evidence[k] = v

    rss_before = _peak_rss_bytes()
    start = time.perf_counter()
    try:
        posterior = inference.infer(artifact, target, state, norm_evidence)
    except ValueError as exc:
        raise ValueError(_bound(str(exc))) from exc
    except Exception as exc:
        raise RuntimeError(_bound(f"inference failed: {exc}")) from exc
    wall = time.perf_counter() - start
    rss_after = _peak_rss_bytes()
    delta = int(max(0, rss_after - rss_before))

    if not math.isfinite(wall) or wall < 0.0:
        raise ValueError(_bound("resource exhausted: invalid wall-time measurement"))
    if wall > timeout:
        raise ValueError(
            _bound(
                f"resource exhausted: inference took {wall:.3f}s over {timeout}s limit"
            )
        )

    base_diags = (
        [str(d) for d in adm_diagnostics] if isinstance(adm_diagnostics, list) else []
    )
    bench_diags = [
        f"dtype={ENGINE_PIN.get('dtype')}",
        f"elimination_order={ENGINE_PIN.get('elimination_order')}",
        f"engine={ENGINE_PIN.get('engine')}:{ENGINE_PIN.get('engine_version')}",
        f"output_bytes={output_bytes}",
        "posterior_computed=true",
        f"request_bytes={request_bytes}",
    ]
    diagnostics_sorted = sorted(base_diags + bench_diags)

    measurements: dict[str, Any] = {
        "xml_bytes": adm_measurements.get("xml_bytes", len(bytes(network_xml))),
        "node_count": adm_measurements.get("node_count", 0),
        "cpt_cells": adm_measurements.get("cpt_cells", 0),
        "request_bytes": request_bytes,
        "output_bytes": output_bytes,
        "inference_wall_s": float(wall),
        "peak_rss_delta_bytes": int(delta),
    }
    return {
        "request_bytes": int(request_bytes),
        "output_bytes": int(output_bytes),
        "inference_wall_s": float(wall),
        "peak_rss_delta_bytes": int(delta),
        "posterior": float(posterior),
        "failure_kind": "ok",
        "measurements": measurements,
        "limits": dict(adm_limits) if isinstance(adm_limits, dict) else {},
        "admitted": True,
        "diagnostics": diagnostics_sorted,
    }
