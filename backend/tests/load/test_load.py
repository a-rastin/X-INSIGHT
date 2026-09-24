"""S58 item 1 (RED): load-harness contract against real PostgreSQL.

Scope: plan.md S58 item 1 / plan.md section 11 planning load (9 physicians
+ admin, 10,000 synthetic patients, ~20 ordinary req/s, 2 provider slots,
7 registration / 6 follow-up questions; ordinary p95 < 1s, provider latency
separate). Seams T1/T8 approved; this slice uses T1 only (public HTTP via
TestClient against the disposable test database). No new seam.

Contract under test (no implementation exists yet; all fail here in red):
- ``x_insight.load.run`` exposes a small deterministic runner taking
  host/dataset/duration-style params. It creates synthetic patients only
  (clearly-labeled synthetic names/IDs, no clinical content, no live
  provider) via public POST /patients and drives concurrent
  saves/searches/polls via threads, computing p95 latencies.
- ``python -m x_insight.load --help`` exits 0 (``make test-load`` wiring).
- The report separates ordinary p95 from provider p95; with no provider
  work the provider section is null/zero.

CI scale is deliberately tiny (5-10 synthetic patients, 2 threads,
seconds) — the full 10k run is the measured manual run in slice 5, not
the CI test. Assertions read the runner's returned report; direct SQL is
used only for per-test isolation (full TRUNCATE list), never for behavior
assertions.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import text

from x_insight import db
from x_insight.identity.throttle import reset_all

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Full repo TRUNCATE list (mirrors tests/http/test_ops_metrics.py) so fixture
# cleanup never blocks on FK references.
_TRUNCATE_TABLES = (
    "encounter_notes, sessions, users, "
    "patients, encounters, runs, run_questions, reasoning_jobs, "
    "reasoning_attempts, run_question_artifacts, run_proposals, "
    "audit_events, model_bundle_pointers, model_bundle_events, "
    "mcp_question_grants, provider_configs, "
    "provider_config_pointer, queue_fairness, ddi_dataset_releases, "
    "recovery_jobs"
)


@pytest.fixture(autouse=True)
def clean_load():
    with db.transaction() as conn:
        conn.execute(text(f"TRUNCATE {_TRUNCATE_TABLES}"))
    reset_all()
    yield
    reset_all()


def test_tiny_synthetic_run_returns_host_dataset_duration_and_p95():
    """Runner exists and a tiny synthetic run reports host/dataset/duration/p95."""
    from x_insight.load import run  # noqa: PLC0415  # RED: ModuleNotFoundError

    result = run(
        host="ci",
        dataset="synthetic-ci-tiny",
        duration_s=5,
        patient_count=5,
        concurrency=2,
    )
    assert isinstance(result, dict)
    assert result["host"] == "ci"
    assert result["dataset"] == "synthetic-ci-tiny"
    assert isinstance(result["duration_s"], (int, float))
    assert result["duration_s"] >= 0
    assert isinstance(result["ordinary_p95_s"], (int, float))
    assert result["ordinary_p95_s"] >= 0


def test_load_module_cli_help_exits_zero():
    """Observable wiring check: the harness CLI answers --help with exit 0."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(_BACKEND_DIR, "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    completed = subprocess.run(
        [sys.executable, "-m", "x_insight.load", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=_BACKEND_DIR,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr


def test_report_separates_provider_latency_from_ordinary_p95():
    """Provider p95 is tracked separately; null/zero when no provider work ran."""
    from x_insight.load import run  # noqa: PLC0415  # RED: ModuleNotFoundError

    result = run(
        host="ci",
        dataset="synthetic-ci-tiny",
        duration_s=5,
        patient_count=5,
        concurrency=2,
    )
    assert result["provider_calls"] == 0
    assert result["provider_p95_s"] is None or result["provider_p95_s"] == 0
    assert isinstance(result["ordinary_p95_s"], (int, float))
