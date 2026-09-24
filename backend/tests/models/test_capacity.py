"""S58 item 2 RED: model-capacity bench harness (T5).

Admission benchmark per plan.md sections 7.4 + 11: measure every admitted
model's complete CPT request/output sizes, exact-inference CPU/memory/time,
and failure behavior; justify admission/resource limits from measurements;
exact inference only (no silent truncation or approximation).

Synthetic mathematical fixtures only (never BNs/ as oracle, never clinical
content, no live provider). Tiny networks; timeouts in seconds.

Proposed public interface (smallest sensible, chosen for this slice)::

    x_insight.models.capacity.measure(
        network_xml: bytes,
        cpt_response: dict,
        queries: list[dict],
        limits: dict | None,
        timeout_s: float,
    ) -> dict

Expected report keys: ``request_bytes`` / ``output_bytes`` (complete CPT
request/output sizes), ``inference_wall_s``, ``peak_rss_delta_bytes``,
``posterior`` (exact, real pinned engine), ``failure_kind`` (``"ok"`` or
``"rejected"``/``"resource_exhausted"``), ``measurements``, ``limits``,
``admitted`` (bool), ``diagnostics`` (deterministic sorted list), and
bounded ``error`` text on failure. Oversized/over-limit networks are
rejected with diagnostics, never truncated. Impossible evidence or timeout
fails loudly with a bounded error, never a silent approximation.

Tiny two-node fixture (hand arithmetic, not from any implementation):
A root [80, 20]; B|A=no [90, 10], B|A=yes [30, 70].
P(B=yes) = 0.8*0.1 + 0.2*0.7 = 0.08 + 0.14 = 0.22.
"""

from __future__ import annotations

import json
from typing import Any

from x_insight.models.capacity import measure  # type: ignore[import-not-found]

POSTERIOR_TOL = 1e-9

# Hand-worked: 0.8*0.1 + 0.2*0.7 = 0.22 (independent of implementation).
EXPECTED_P_B_YES = 0.22

_TINY_XML = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>SyntheticCapacityTiny</NAME>'
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)

# Deterministic zero-mass root: P(A=yes) = 0, so evidence {A: yes} has
# joint probability zero (impossible evidence, hand arithmetic).
_ZERO_MASS_XML = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>SyntheticCapacityZero</NAME>'
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>1.0 0.0</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)


def _tiny_response() -> dict[str, Any]:
    return {
        "question_key": "synthetic_capacity_tiny",
        "network_version": "v1",
        "network_hash": "synthetic",
        "tables": [
            {
                "node_id": "A",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [80, 20]}],
            },
            {
                "node_id": "B",
                "parent_ids": ["A"],
                "states": ["no", "yes"],
                "rows": [
                    {"parent_states": ["no"], "percentages": [90, 10]},
                    {"parent_states": ["yes"], "percentages": [30, 70]},
                ],
            },
        ],
    }


def _tiny_query() -> list[dict[str, Any]]:
    return [{"target": "B", "state": "yes", "evidence": {}}]


def test_measure_tiny_network_reports_sizes_timing_and_posterior() -> None:
    """Bench on a tiny synthetic 2-node network returns sizes, wall time,
    peak RSS delta, hand-checked posterior, and rejects oversized input."""
    report = measure(
        _TINY_XML,
        _tiny_response(),
        _tiny_query(),
        limits=None,
        timeout_s=10.0,
    )
    assert report["request_bytes"] > 0
    assert report["output_bytes"] > 0
    assert report["inference_wall_s"] >= 0.0
    assert report["inference_wall_s"] < 10.0
    assert isinstance(report["peak_rss_delta_bytes"], int)
    # Posterior sanity from independent hand arithmetic, not the impl.
    assert abs(float(report["posterior"]) - EXPECTED_P_B_YES) <= POSTERIOR_TOL

    oversized_xml = b"<BIF>" + b"x" * 300000 + b"</BIF>"
    rejected = measure(
        oversized_xml,
        _tiny_response(),
        _tiny_query(),
        limits={"max_xml_bytes": 100},
        timeout_s=10.0,
    )
    assert rejected["failure_kind"] == "rejected"
    assert rejected["admitted"] is False
    assert len(rejected["diagnostics"]) > 0
    # Rejected, not truncated: no posterior served for over-limit input.
    assert "posterior" not in rejected


def test_bench_report_justifies_admission_limits() -> None:
    """Bench report carries measurements + limits + admitted flag +
    deterministic sorted diagnostics for admitted and rejected cases."""
    admitted = measure(
        _TINY_XML,
        _tiny_response(),
        _tiny_query(),
        limits=None,
        timeout_s=10.0,
    )
    for key in ("measurements", "limits", "admitted", "diagnostics"):
        assert key in admitted
    assert admitted["admitted"] is True
    assert admitted["diagnostics"] == sorted(admitted["diagnostics"])
    # Complete CPT sizes are measured, so limits are justified from data.
    assert admitted["measurements"]["xml_bytes"] > 0
    assert admitted["request_bytes"] > 0
    assert admitted["output_bytes"] > 0
    assert admitted["request_bytes"] <= int(
        json.dumps(_tiny_response()).__len__() + len(_TINY_XML) + 4096
    )

    rejected = measure(
        _TINY_XML,
        _tiny_response(),
        _tiny_query(),
        limits={"max_nodes": 1},
        timeout_s=10.0,
    )
    assert rejected["admitted"] is False
    assert rejected["diagnostics"] == sorted(rejected["diagnostics"])
    assert len(rejected["diagnostics"]) > 0
    assert rejected["failure_kind"] == "rejected"


def test_resource_exhaustion_fails_loudly_never_silently() -> None:
    """Impossible evidence or timeout raises a bounded loud error, never a
    silent approximation."""
    zero_response = _tiny_response()
    zero_response["tables"] = [
        {
            "node_id": "A",
            "parent_ids": [],
            "states": ["no", "yes"],
            "rows": [{"parent_states": [], "percentages": [100, 0]}],
        },
        {
            "node_id": "B",
            "parent_ids": ["A"],
            "states": ["no", "yes"],
            "rows": [
                {"parent_states": ["no"], "percentages": [90, 10]},
                {"parent_states": ["yes"], "percentages": [30, 70]},
            ],
        },
    ]
    impossible_query = [{"target": "B", "state": "yes", "evidence": {"A": "yes"}}]
    try:
        report = measure(
            _ZERO_MASS_XML,
            zero_response,
            impossible_query,
            limits=None,
            timeout_s=10.0,
        )
    except ValueError as exc:
        assert "impossible evidence" in str(exc) or "resource exhausted" in str(exc)
        assert len(str(exc)) <= 500
    else:
        assert report.get("failure_kind") in ("rejected", "resource_exhausted")
        assert "posterior" not in report
        assert len(str(report.get("error", ""))) <= 500

    try:
        measure(
            _TINY_XML,
            _tiny_response(),
            _tiny_query(),
            limits=None,
            timeout_s=0.0,
        )
    except ValueError as exc:
        assert "resource exhausted" in str(exc)
        assert len(str(exc)) <= 500
    else:  # pragma: no cover - implementation must fail loudly
        raise AssertionError("zero timeout must fail loudly, never approximate")
