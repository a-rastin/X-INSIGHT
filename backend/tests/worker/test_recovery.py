"""S47 slice 1 (RED): bounded retry budget with backoff (T1/T8).

Tasks.md S47.1; plan.md 8.5; FR-36, FR-43, NFR-04; seams T1 + T8 only.

Synthetic 2-node A->B network only (same bytes as test_workflows.py,
never BNs/, never clinical, never a released default). Three-question
registration bundle (s47_q1 succeeds, s47_q2 fails 3x, s47_q3 never
runs) proves prior-section retention and later-pending. Controlled
localhost provider only (X_INSIGHT_PROVIDER_ALLOW_LOCAL=true); real
PostgreSQL + real MCP + public T1 GET /runs + T8 run_once. Setup-only
direct SQL for bundles/provider; all assertions read public GET JSON +
captured provider bodies, never SQL rows.

Failure injection goes through real HTTP status codes / real response
bodies via the controlled provider (no mocking of owned modules):
- q2 attempt 1 -> 500 transient (retryable)
- q2 attempt 2 -> 200 with invalid CPT JSON (percentages sum != 100)
- q2 attempt 3 -> 429 rate-limited with Retry-After (retryable)
Provider adapter must not retry internally: exactly one POST per
attempt, so q2 must show exactly 3 bodies (one per attempt).

EXPECTED RED: current worker/coordinator has no shared retry budget:
the first q2 failure marks the job/run terminal failed immediately
(no backoff/available_at, no 3-attempt budget). Both the intermediate
retryable assertion and the final 3-body/attempt_count==3 assertions
fail on current code (q2 shows exactly 1 body, attempt_count 1,
terminal failed after the first error).
"""

from __future__ import annotations

import hashlib
import http.server
import json
import socketserver
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all

SYNTHETIC_HISTORY_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "content" / "history"
)

SYNTHETIC_NETWORK_VERSION = "v1"
SYNTHETIC_HISTORY_VERSION = "synthetic-history-v1"
SYNTHETIC_MODEL = "synthetic-model-s47"
SYNTHETIC_API_KEY = "synthetic-provider-key-s47-001"

SENTINEL_FIRST = "SentinelAlpha"
SENTINEL_LAST = "SentinelBeta"
SENTINEL_PHONE = "SENTINEL-PHONE-0047"

# Same bytes as backend/tests/worker/test_workflows.py (plan.md 7.4).
SYNTHETIC_XML = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>SyntheticCPT</NAME>'
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)

NETWORK_HASH = hashlib.sha256(SYNTHETIC_XML).hexdigest()

Q1 = "s47_q1"
Q2 = "s47_q2"
Q3 = "s47_q3"


@pytest.fixture(autouse=True)
def clean_recovery(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    _truncate_all()
    reset_all()
    yield
    _truncate_all()
    reset_all()


def _truncate_all() -> None:
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, runs, run_questions, reasoning_jobs, "
                "reasoning_attempts, run_question_artifacts, run_proposals, "
                "audit_events, model_bundle_pointers, model_bundle_events, "
                "mcp_question_grants, provider_configs, "
                "provider_config_pointer, queue_fairness, ddi_dataset_releases"
            )
        )


def _login(client, username="admin", password="admin", role="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200


def _mutation_headers(client, *, key=None, revision=None):
    headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
    if key is not None:
        headers["Idempotency-Key"] = key
    if revision is not None:
        headers["If-Match"] = str(revision)
    return headers


def _make_physician(admin, username):
    created = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "secret"},
        headers=_mutation_headers(admin, key=f"s47-{username}-create"),
    )
    assert created.status_code == 201


def _create_sentinel_patient(physician, patient_id, key):
    response = physician.post(
        "/api/v1/patients",
        json={
            "first_name": SENTINEL_FIRST,
            "last_name": SENTINEL_LAST,
            "sex": "F",
            "age": 30,
            "patient_id": patient_id,
            "clinical_status": "first_time",
            "phone": SENTINEL_PHONE,
        },
        headers=_mutation_headers(physician, key=key),
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["patient"], payload["encounter"]


def _current_revision(physician, encounter_id) -> int:
    fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
    assert fetched.status_code == 200
    return int(fetched.json()["encounter"]["revision"])


def _clinical_draft() -> dict[str, Any]:
    return {
        "diagnosis": {"answers": {"synthetic_item": "synthetic_value"}},
        "history": {
            "definition_version": SYNTHETIC_HISTORY_VERSION,
            "values": {"synthetic_flag_true": {"status": "known", "value": True}},
        },
        "effects": {
            "definition_version": SYNTHETIC_HISTORY_VERSION,
            "values": {
                "tardive_dyskinesia": {
                    "status": "present",
                    "severity": "synthetic_tardive_severity_one",
                },
                "akathisia": {"status": "absent", "severity": None},
                "parkinsonism": {"status": "absent", "severity": None},
                "acute_dystonia": {"status": "not_assessed", "severity": None},
            },
        },
        "medications": [{"catalog_drug_id": "synthetic-med-a"}],
        "ddi_report": {
            "dataset_version": "synthetic-ddi-s47",
            "medication_fingerprint": "fp-synth-s47",
        },
    }


def _synthetic_cpt_payload(question_key: str) -> dict:
    return {
        "question_key": question_key,
        "network_version": SYNTHETIC_NETWORK_VERSION,
        "network_hash": NETWORK_HASH,
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


def _invalid_cpt_payload(question_key: str) -> dict:
    """Same shape but bad percentages sum (30+60=90, not 100)."""
    payload = _synthetic_cpt_payload(question_key)
    payload["tables"][1]["rows"][1] = {
        "parent_states": ["yes"],
        "percentages": [30, 60],
    }
    return payload


def _make_question(key: str, index: int) -> dict[str, Any]:
    return {
        "question_key": key,
        "version": SYNTHETIC_NETWORK_VERSION,
        "network_hash": NETWORK_HASH,
        "network_xml": SYNTHETIC_XML.decode("utf-8"),
        "prompt": (
            f"SYNTH-S47-{key} SYNTH-Q{index} estimate every CPT as "
            "percentages summing to 100 using only listed patient "
            "facts. Do not write a plan. Do not choose applicability."
        ),
        "template": {"template_version": "synthetic-v1"},
    }


def _insert_bundle(
    workflow: str, revision: int, bundle_hash: str, questions: list[dict]
) -> None:
    pins = {"questions": questions}
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO model_bundle_pointers "
                "(workflow, revision, bundle_hash, pins) "
                "VALUES (:workflow, :revision, :hash, CAST(:pins AS jsonb)) "
                "ON CONFLICT (workflow) DO UPDATE SET revision = :revision, "
                "bundle_hash = :hash, pins = CAST(:pins AS jsonb)"
            ),
            {
                "workflow": workflow,
                "revision": revision,
                "hash": bundle_hash,
                "pins": json.dumps(pins),
            },
        )
        conn.execute(
            text(
                "INSERT INTO model_bundle_events "
                "(workflow, revision, bundle_hash, pins, action) "
                "VALUES (:workflow, :revision, :hash, CAST(:pins AS jsonb), "
                "'activate') ON CONFLICT (workflow, revision) DO NOTHING"
            ),
            {
                "workflow": workflow,
                "revision": revision,
                "hash": bundle_hash,
                "pins": json.dumps(pins),
            },
        )


def _insert_provider_config(base_url: str) -> None:
    from x_insight.reasoning.provider_config import encrypt_api_key

    ciphertext = encrypt_api_key(SYNTHETIC_API_KEY)
    with db.transaction() as conn:
        row = (
            conn.execute(
                text(
                    "INSERT INTO provider_configs "
                    "(revision, base_url, model, key_ciphertext, "
                    " key_present, test_status) "
                    "VALUES (1, :base_url, :model, :ciphertext, TRUE, "
                    " 'untested') RETURNING id"
                ),
                {
                    "base_url": base_url,
                    "model": SYNTHETIC_MODEL,
                    "ciphertext": ciphertext,
                },
            )
            .mappings()
            .one()
        )
        conn.execute(
            text(
                "INSERT INTO provider_config_pointer "
                "(id, active_config_id, active_revision) "
                "VALUES (1, :id, 1) "
                "ON CONFLICT (id) DO UPDATE SET "
                "active_config_id = EXCLUDED.active_config_id, "
                "active_revision = EXCLUDED.active_revision"
            ),
            {"id": str(row["id"])},
        )


def _body_question_key(raw: bytes) -> str | None:
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    network_contract = data.get("network_contract")
    if isinstance(network_contract, dict) and isinstance(
        network_contract.get("question_key"), str
    ):
        return str(network_contract["question_key"])
    return None


def _start_provider(bodies: list[bytes]):
    """Controlled localhost provider with the S47.1 failure sequence.

    Real HTTP status codes / real response bodies (no owned-module mocks):
    - s47_q1 / s47_q3 -> 200 valid CPTs.
    - s47_q2 attempt 1 -> 500 transient; attempt 2 -> 200 invalid CPT
      (bad percentages sum); attempt 3+ -> 429 rate-limited with
      Retry-After. Exactly one POST per attempt (no nested adapter retries).
    """
    lock = threading.Lock()
    valid_by_key = {
        Q1: _synthetic_cpt_payload(Q1),
        Q2: _synthetic_cpt_payload(Q2),
        Q3: _synthetic_cpt_payload(Q3),
    }
    invalid_q2 = _invalid_cpt_payload(Q2)

    def _send(
        handler, status: int, payload: dict, extra_headers: dict | None = None
    ) -> None:
        out = json.dumps(payload).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(out)))
        for name, value in (extra_headers or {}).items():
            handler.send_header(name, value)
        handler.end_headers()
        handler.wfile.write(out)

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            with lock:
                bodies.append(raw)
                q2_count = sum(1 for b in bodies if _body_question_key(b) == Q2)
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                data = {}
            network_contract = (
                data.get("network_contract") if isinstance(data, dict) else None
            )
            qkey = (
                network_contract.get("question_key")
                if isinstance(network_contract, dict)
                else None
            )
            if qkey == Q2:
                if q2_count == 1:
                    _send(self, 500, {"error": "synthetic transient"})
                elif q2_count == 2:
                    _send(self, 200, invalid_q2)
                else:
                    _send(
                        self,
                        429,
                        {"error": "synthetic rate limited"},
                        {"Retry-After": "1"},
                    )
                return
            payload = valid_by_key.get(qkey) if isinstance(qkey, str) else None
            if payload is None:
                payload = valid_by_key[Q1]
            _send(self, 200, payload)

        def log_message(self, *args) -> None:
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    return server, thread


def _start_run(physician, encounter_id, revision, key: str) -> str:
    started = physician.post(
        f"/api/v1/encounters/{encounter_id}/runs",
        json={"encounter_revision": revision},
        headers=_mutation_headers(physician, key=key, revision=revision),
    )
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    uuid.UUID(run_id)
    return run_id


def _get_run(physician, run_id: str) -> dict:
    fetched = physician.get(f"/api/v1/runs/{run_id}")
    assert fetched.status_code == 200
    return fetched.json()


def _drain_with_backoff(worker_prefix: str, max_steps: int = 15) -> list[dict]:
    """Drain via public T8 run_once, skipping past the 60s backoff cap.

    Deterministic queue-clock jumps (same pattern as S44 slice-4) let a
    correct shared budget/backoff implementation reach all 3 attempts
    without real sleeps. Clock control is harness-only; every assertion
    still reads public GET JSON + captured provider bodies. On current
    code (no backoff) the jumps are no-ops and the drain stops after the
    single terminal failure.
    """
    from datetime import timedelta

    from x_insight.reasoning import queue as queue_module
    from x_insight.reasoning.worker import run_once as _real_run_once

    outcomes: list[dict] = []
    base = queue_module.now_utc()
    offset = timedelta(0)
    queue_module.set_now_fn(lambda: base + offset)
    try:
        for step in range(max_steps):
            try:
                outcome = _real_run_once(
                    database_url=None,
                    provider_adapter=None,
                    worker_id=f"{worker_prefix}-{step}",
                )
            except Exception as exc:  # noqa: BLE001 - failure attempts raise
                outcomes.append(
                    {"claimed": True, "raised": type(exc).__name__, "step": step}
                )
                continue
            outcomes.append(outcome)
            if not outcome.get("claimed"):
                offset += timedelta(seconds=65)
                trailing_idle = 0
                for past in reversed(outcomes):
                    if not past.get("claimed") or past.get("raised"):
                        if past.get("raised"):
                            break
                        trailing_idle += 1
                    else:
                        break
                if trailing_idle >= 2:
                    break
    finally:
        queue_module.reset_now_fn()
    return outcomes


# ---------------------------------------------------------------------------
# S47 slice 1: timeout -> invalid CPT -> rate-limit exhausts three attempts.
# ---------------------------------------------------------------------------


def test_timeout_invalid_ratelimit_exhausts_three_attempts() -> None:
    """Three mixed failures exhaust one shared 3-attempt budget (RED).

    q1 succeeds; q2 fails 500 -> invalid CPT -> 429 across exactly 3
    provider POSTs (one per attempt, no nested adapter retries); q3 never
    runs. Prior section + draft are retained, later work stays pending,
    budget exhaustion blocks a 4th POST.

    RED: no retry budget exists — the first q2 failure marks the job/run
    terminal failed immediately (1 q2 body, attempt_count 1), so both the
    intermediate retryable assertion and the final 3-body assertion fail.
    """
    from x_insight.reasoning.worker import run_once

    bundle_hash = "synthetic-bundle-hash-s47-slice1"
    questions = [_make_question(Q1, 1), _make_question(Q2, 2), _make_question(Q3, 3)]
    bodies: list[bytes] = []

    server, thread = _start_provider(bodies)
    try:
        host, port = server.server_address
        _insert_bundle("registration", 1, bundle_hash, questions)
        _insert_provider_config(f"http://{host}:{port}")

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s47docA")
            _login(physician, "s47docA", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000471", "s47-s1-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_id = _start_run(physician, encounter_id, revision, "s47-s1-run-1")

            # q1 succeeds on the first claimed step (no exception).
            first = run_once(
                database_url=None, provider_adapter=None, worker_id="s47-s1-q1"
            )
            assert first.get("claimed") is True
            assert first.get("question_key") == Q1
            assert sum(1 for b in bodies if _body_question_key(b) == Q1) == 1

            # q2 attempt 1 (500 transient) must NOT go terminal: the shared
            # budget keeps the job retryable with backoff eligibility.
            try:
                run_once(
                    database_url=None, provider_adapter=None, worker_id="s47-s1-q2a"
                )
                q2_first_raised = False
            except Exception:  # noqa: BLE001 - retryable failure surfaces
                q2_first_raised = True
            assert q2_first_raised is True
            assert sum(1 for b in bodies if _body_question_key(b) == Q2) == 1
            intermediate = _get_run(physician, run_id)
            q2_intermediate = next(
                j for j in intermediate["jobs"] if j["question_key"] == Q2
            )
            # RED: current code marks failed immediately; budget requires
            # a still-retryable (queued/claimed) job after attempt 1.
            assert q2_intermediate["status"] in ("queued", "claimed")
            assert q2_intermediate["attempt_count"] == 1

            # Drain the remaining budget (invalid CPT, then 429) past the
            # shared backoff cap; q3 must never be called.
            _drain_with_backoff("s47-s1", max_steps=15)

            q2_bodies = [b for b in bodies if _body_question_key(b) == Q2]
            q3_bodies = [b for b in bodies if _body_question_key(b) == Q3]
            # One POST per attempt, no nested adapter retries.
            assert len(q2_bodies) == 3
            assert q3_bodies == []
            assert sum(1 for b in bodies if _body_question_key(b) == Q1) == 1

            body = _get_run(physician, run_id)
            by_job = {j["question_key"]: j for j in body["jobs"]}
            assert by_job[Q1]["status"] == "succeeded"
            assert by_job[Q2]["status"] == "failed"
            assert by_job[Q2]["attempt_count"] == 3
            assert Q3 not in by_job
            assert body["run"]["status"] == "failed"
            # Prior section retained; later questions pending; no proposal.
            assert [s["question_key"] for s in body["sections"]] == [Q1]
            assert body.get("proposal") is None

            # Budget exhausted: immediate reclaim issues no 4th q2 POST.
            n_before = len(q2_bodies)
            try:
                run_once(
                    database_url=None,
                    provider_adapter=None,
                    worker_id="s47-s1-extra",
                )
            except Exception:  # noqa: BLE001 - terminal state stays failed
                pass
            assert len([b for b in bodies if _body_question_key(b) == Q2]) == n_before
            reread = _get_run(physician, run_id)
            assert reread["run"]["status"] == "failed"
            assert [s["question_key"] for s in reread["sections"]] == [Q1]

            # Draft remains readable and unmodified by the failure.
            draft = physician.get(f"/api/v1/encounters/{encounter_id}")
            assert draft.status_code == 200
            assert draft.json()["encounter"]["state"] == "draft"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S47 slice 2a (RED): author retry of unchanged failed stage (T1/T8).
#
# Expected retry contract (plan.md 4.3 + 8.5, MCP-design retry row):
# POST /runs/{run_id}/retry with body
#   {question_key, failed_stage, expected_run_revision}
# where failed_stage is one of estimating_cpts/inferring/rendering.
# - 202: unchanged inputs + matching run revision; starts a new bounded
#   batch at the failed stage, prior attempt history retained. The body
#   cannot select another snapshot or swap pinned settings (pinned
#   bundle/snapshot_hash byte-identical after retry).
# - 401 anon; 403 non-author (including admin); 412 stale
#   expected_run_revision; 409 changed analytical inputs (live fingerprint
#   != run fingerprint) with a clear message. 409 chosen over 422 because
#   the inputs were valid but conflict with the frozen run snapshot.
#
# RED: the route does not exist yet, so every retry POST below returns 404.
# The failure setup itself is green on slice-1 code (3-attempt exhaustion).
# ---------------------------------------------------------------------------


def _start_provider_fail_then_succeed(bodies: list[bytes]):
    """q1 always valid; q2 500 -> invalid CPT -> 429, then valid (retry)."""
    lock = threading.Lock()
    valid_by_key = {
        Q1: _synthetic_cpt_payload(Q1),
        Q2: _synthetic_cpt_payload(Q2),
        Q3: _synthetic_cpt_payload(Q3),
    }
    invalid_q2 = _invalid_cpt_payload(Q2)

    def _send(
        handler, status: int, payload: dict, extra_headers: dict | None = None
    ) -> None:
        out = json.dumps(payload).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(out)))
        for name, value in (extra_headers or {}).items():
            handler.send_header(name, value)
        handler.end_headers()
        handler.wfile.write(out)

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            with lock:
                bodies.append(raw)
                q2_count = sum(1 for b in bodies if _body_question_key(b) == Q2)
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                data = {}
            network_contract = (
                data.get("network_contract") if isinstance(data, dict) else None
            )
            qkey = (
                network_contract.get("question_key")
                if isinstance(network_contract, dict)
                else None
            )
            if qkey == Q2:
                if q2_count == 1:
                    _send(self, 500, {"error": "synthetic transient"})
                elif q2_count == 2:
                    _send(self, 200, invalid_q2)
                elif q2_count == 3:
                    _send(
                        self,
                        429,
                        {"error": "synthetic rate limited"},
                        {"Retry-After": "1"},
                    )
                else:
                    _send(self, 200, valid_by_key[Q2])
                return
            payload = valid_by_key.get(qkey) if isinstance(qkey, str) else None
            if payload is None:
                payload = valid_by_key[Q1]
            _send(self, 200, payload)

        def log_message(self, *args) -> None:
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    return server, thread


def _mutated_clinical_draft() -> dict[str, Any]:
    """Same shape as _clinical_draft with one flipped analytical fact."""
    draft = _clinical_draft()
    draft["history"] = {
        "definition_version": SYNTHETIC_HISTORY_VERSION,
        "values": {"synthetic_flag_true": {"status": "known", "value": False}},
    }
    return draft


def test_manual_retry_starts_new_bounded_batch_without_repeating_q1() -> None:
    """Author retry of unchanged q2 starts a new bounded batch (RED).

    q1 succeeds once; q2 exhausts 3 attempts (500 -> invalid -> 429).
    Author POST /runs/{run_id}/retry {q2, estimating_cpts, run revision}
    must return 202 and the drained retry must succeed with exactly one
    more q2 POST and no new q1 POST; sections become [q1, q2]; prior
    attempt history is retained; pinned bundle/snapshot are unchanged.
    Auth/stale/changed-input rejections (401/403/412/409) are asserted.

    RED: route missing -> every retry POST returns 404.
    """
    from x_insight.reasoning.worker import run_once

    bundle_hash = "synthetic-bundle-hash-s47-slice2a"
    questions = [_make_question(Q1, 1), _make_question(Q2, 2)]
    bodies: list[bytes] = []

    server, thread = _start_provider_fail_then_succeed(bodies)
    try:
        host, port = server.server_address
        _insert_bundle("registration", 1, bundle_hash, questions)
        _insert_provider_config(f"http://{host}:{port}")

        with (
            TestClient(app) as admin,
            TestClient(app) as physician,
            TestClient(app) as other,
            TestClient(app) as anon,
        ):
            _login(admin)
            _make_physician(admin, "s47docB")
            _make_physician(admin, "s47docB2")
            _login(physician, "s47docB", "secret", "physician")
            _login(other, "s47docB2", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000472", "s47-s2a-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_id = _start_run(physician, encounter_id, revision, "s47-s2a-run-1")

            first = run_once(
                database_url=None, provider_adapter=None, worker_id="s47-s2a-q1"
            )
            assert first.get("claimed") is True
            assert first.get("question_key") == Q1
            assert sum(1 for b in bodies if _body_question_key(b) == Q1) == 1

            _drain_with_backoff("s47-s2a", max_steps=15)
            assert sum(1 for b in bodies if _body_question_key(b) == Q2) == 3
            assert sum(1 for b in bodies if _body_question_key(b) == Q1) == 1

            body = _get_run(physician, run_id)
            by_job = {j["question_key"]: j for j in body["jobs"]}
            assert by_job[Q2]["status"] == "failed"
            assert by_job[Q2]["attempt_count"] == 3
            assert [s["question_key"] for s in body["sections"]] == [Q1]
            assert body["run"]["status"] == "failed"
            run_rev = int(body["run"]["revision"])
            pinned_before = body["pinned"]
            snapshot_before = body["snapshot_hash"]

            retry_body = {
                "question_key": Q2,
                "failed_stage": "estimating_cpts",
                "expected_run_revision": run_rev,
            }
            retry_url = f"/api/v1/runs/{run_id}/retry"

            anon_denied = anon.post(retry_url, json=retry_body)
            assert anon_denied.status_code == 401

            other_denied = other.post(
                retry_url,
                json=retry_body,
                headers=_mutation_headers(other, key="s47-s2a-other"),
            )
            assert other_denied.status_code == 403

            admin_denied = admin.post(
                retry_url,
                json=retry_body,
                headers=_mutation_headers(admin, key="s47-s2a-admin"),
            )
            assert admin_denied.status_code == 403

            stale_denied = physician.post(
                retry_url,
                json={**retry_body, "expected_run_revision": run_rev + 999},
                headers=_mutation_headers(physician, key="s47-s2a-stale"),
            )
            assert stale_denied.status_code == 412

            # Changed analytical inputs conflict with the frozen snapshot.
            changed_rev = _current_revision(physician, encounter_id)
            patched = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _mutated_clinical_draft()},
                headers=_mutation_headers(physician, revision=changed_rev),
            )
            assert patched.status_code == 200
            changed_denied = physician.post(
                retry_url,
                json=retry_body,
                headers=_mutation_headers(physician, key="s47-s2a-changed"),
            )
            assert changed_denied.status_code == 409
            restored_rev = _current_revision(physician, encounter_id)
            restored = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=restored_rev),
            )
            assert restored.status_code == 200

            # RED: 404 until the retry route exists; green must return 202.
            accepted = physician.post(
                retry_url,
                json=retry_body,
                headers=_mutation_headers(physician, key="s47-s2a-retry"),
            )
            assert accepted.status_code == 202

            _drain_with_backoff("s47-s2a-retry", max_steps=15)
            assert sum(1 for b in bodies if _body_question_key(b) == Q2) == 4
            assert sum(1 for b in bodies if _body_question_key(b) == Q1) == 1

            after = _get_run(physician, run_id)
            assert [s["question_key"] for s in after["sections"]] == [Q1, Q2]
            q2_attempts = sum(
                j["attempt_count"] for j in after["jobs"] if j["question_key"] == Q2
            )
            assert q2_attempts >= 4
            assert after["pinned"] == pinned_before
            assert after["snapshot_hash"] == snapshot_before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S47 slice 2b (RED): stage resume reuses artifacts, no new provider POSTs.
#
# Harness-only failure injection (no owned-module mocking of the unit under
# test): monkeypatch x_insight.reasoning.coordinator.infer and
# .render_section to raise CoordinatorError exactly once each, so the real
# worker path records a terminal stage failure after a real provider POST.
# Green must persist accepted CPTs before inference and the inference
# result before rendering, so manual retry resumes the failed stage with
# zero additional provider POSTs for that question.
#
# RED: the retry route does not exist, so the first retry POST returns 404.
# ---------------------------------------------------------------------------


def _start_provider_always_valid(bodies: list[bytes]):
    """Always-200 valid CPTs for any question key (stage-failure tests)."""
    lock = threading.Lock()
    valid_by_key = {
        Q1: _synthetic_cpt_payload(Q1),
        Q2: _synthetic_cpt_payload(Q2),
    }

    def _send(handler, status: int, payload: dict) -> None:
        out = json.dumps(payload).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(out)))
        handler.end_headers()
        handler.wfile.write(out)

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            with lock:
                bodies.append(raw)
            qkey = _body_question_key(raw)
            _send(self, 200, valid_by_key.get(qkey, valid_by_key[Q1]))

        def log_message(self, *args) -> None:
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    return server, thread


def test_stage_retry_reuses_cpts_and_result_without_new_posts(monkeypatch) -> None:
    """Inference/rendering retry reuses stored artifacts (RED).

    q1 fails once at inference (harness-injected CoordinatorError after one
    real provider POST); retry resumes inference with no new q1 POST.
    q2 then fails once at rendering; retry resumes rendering with no new
    q2 POST. Sections end [q1, q2]; q1 bodies stay 1 throughout.

    RED: first retry POST returns 404 (route missing).
    """
    from x_insight.reasoning import coordinator as coordinator_module
    from x_insight.reasoning.coordinator import CoordinatorError
    from x_insight.reasoning.worker import run_once

    bundle_hash = "synthetic-bundle-hash-s47-slice2b"
    questions = [_make_question(Q1, 1), _make_question(Q2, 2)]
    bodies: list[bytes] = []

    real_infer = coordinator_module.infer
    real_render = coordinator_module.render_section
    infer_injected = {"count": 0}
    render_injected = {"count": 0}

    def _flaky_infer(artifact, target, state, evidence):
        if infer_injected["count"] == 0:
            infer_injected["count"] += 1
            raise CoordinatorError("synthetic inference failure (harness-only)")
        return real_infer(artifact, target, state, evidence)

    def _flaky_render(template, question_key, version, accepted, query, posterior):
        if question_key == Q2 and render_injected["count"] == 0:
            render_injected["count"] += 1
            raise CoordinatorError("synthetic rendering failure (harness-only)")
        return real_render(template, question_key, version, accepted, query, posterior)

    monkeypatch.setattr(coordinator_module, "infer", _flaky_infer)
    monkeypatch.setattr(coordinator_module, "render_section", _flaky_render)

    server, thread = _start_provider_always_valid(bodies)
    try:
        host, port = server.server_address
        _insert_bundle("registration", 1, bundle_hash, questions)
        _insert_provider_config(f"http://{host}:{port}")

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s47docD")
            _login(physician, "s47docD", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000473", "s47-s2b-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_id = _start_run(physician, encounter_id, revision, "s47-s2b-run-1")
            retry_url = f"/api/v1/runs/{run_id}/retry"

            # q1: one real POST, then harness-injected inference failure.
            try:
                run_once(
                    database_url=None, provider_adapter=None, worker_id="s47-s2b-q1"
                )
                q1_raised = False
            except Exception:  # noqa: BLE001 - stage failure surfaces
                q1_raised = True
            assert q1_raised is True
            assert infer_injected["count"] == 1
            assert sum(1 for b in bodies if _body_question_key(b) == Q1) == 1
            failed_q1 = _get_run(physician, run_id)
            q1_job = next(j for j in failed_q1["jobs"] if j["question_key"] == Q1)
            assert q1_job["status"] == "failed"
            run_rev = int(failed_q1["run"]["revision"])

            # RED: 404 until the retry route exists; green must return 202.
            retry_q1 = physician.post(
                retry_url,
                json={
                    "question_key": Q1,
                    "failed_stage": "inferring",
                    "expected_run_revision": run_rev,
                },
                headers=_mutation_headers(physician, key="s47-s2b-retry-q1"),
            )
            assert retry_q1.status_code == 202

            _drain_with_backoff("s47-s2b-retry-q1", max_steps=15)
            # Inference resume reuses accepted CPTs: no new q1 POST.
            assert sum(1 for b in bodies if _body_question_key(b) == Q1) == 1
            resumed_q1 = _get_run(physician, run_id)
            assert [s["question_key"] for s in resumed_q1["sections"]] == [Q1]
            assert (
                sum(
                    j["attempt_count"]
                    for j in resumed_q1["jobs"]
                    if j["question_key"] == Q1
                )
                >= 2
            )

            # q2: one real POST, then harness-injected rendering failure.
            _drain_with_backoff("s47-s2b-q2", max_steps=15)
            assert render_injected["count"] == 1
            assert sum(1 for b in bodies if _body_question_key(b) == Q2) == 1
            failed_q2 = _get_run(physician, run_id)
            q2_job = next(j for j in failed_q2["jobs"] if j["question_key"] == Q2)
            assert q2_job["status"] == "failed"

            retry_q2 = physician.post(
                retry_url,
                json={
                    "question_key": Q2,
                    "failed_stage": "rendering",
                    "expected_run_revision": int(failed_q2["run"]["revision"]),
                },
                headers=_mutation_headers(physician, key="s47-s2b-retry-q2"),
            )
            assert retry_q2.status_code == 202

            _drain_with_backoff("s47-s2b-retry-q2", max_steps=15)
            # Rendering resume reuses stored result: no new q2 POST.
            assert sum(1 for b in bodies if _body_question_key(b) == Q2) == 1
            assert sum(1 for b in bodies if _body_question_key(b) == Q1) == 1
            done = _get_run(physician, run_id)
            assert [s["question_key"] for s in done["sections"]] == [Q1, Q2]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S47 slice 3a (RED): crash after attempt start consumes the recorded
# attempt; resume preserves counters and never duplicates sections (T1/T8).
#
# Plan.md 8.5 crash/restart row: "persist attempt start before outbound
# work" + "resume from persisted artifacts/attempt counter after lease
# recovery; an uncertain in-flight request consumes its recorded attempt".
#
# Crash model: the worker holds only DB + lease state, so dropping the
# in-memory claim after queue.begin_attempt (no finish, no provider call)
# plus engine disposal is a faithful in-process crash. Recovery is lease
# expiry + reclaim through the public T8 run_once entry; every assertion
# reads public GET /runs JSON + captured provider bodies, never SQL rows.
#
# RED: queue.begin_attempt does not exist yet (AttributeError on setup).
# ---------------------------------------------------------------------------


def test_crash_after_attempt_start_consumes_attempt_and_resumes() -> None:
    """Crashed in-flight attempt is consumed; resume keeps counts/sections."""
    from datetime import timedelta

    from x_insight import db as db_module
    from x_insight.reasoning import queue as queue_module
    from x_insight.reasoning.worker import run_once

    bundle_hash = "synthetic-bundle-hash-s47-slice3a"
    questions = [_make_question(Q1, 1), _make_question(Q2, 2)]
    bodies: list[bytes] = []

    server, thread = _start_provider_always_valid(bodies)
    try:
        host, port = server.server_address
        _insert_bundle("registration", 1, bundle_hash, questions)
        _insert_provider_config(f"http://{host}:{port}")

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s47docE")
            _login(physician, "s47docE", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000474", "s47-s3a-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_id = _start_run(physician, encounter_id, revision, "s47-s3a-run-1")

            # Crash between attempt start and any outbound work.
            claim = queue_module.claim_next_job(worker_id="s47-s3a-crash")
            assert claim is not None
            assert claim["question_key"] == Q1
            started = queue_module.begin_attempt(
                str(claim["job_id"]), str(claim["lease_token"])
            )
            assert started == 1
            db_module.dispose_engines()
            del claim

            crashed = _get_run(physician, run_id)
            q1_crashed = next(j for j in crashed["jobs"] if j["question_key"] == Q1)
            assert q1_crashed["status"] == "claimed"
            assert q1_crashed["attempt_count"] == 1
            assert crashed["sections"] == []
            assert bodies == []

            # Lease expiry + reclaim through the public worker entry.
            base = queue_module.now_utc()
            queue_module.set_now_fn(lambda: base + timedelta(seconds=130))
            try:
                resumed = run_once(
                    database_url=None,
                    provider_adapter=None,
                    worker_id="s47-s3a-resume",
                )
            finally:
                queue_module.reset_now_fn()
            assert resumed.get("claimed") is True
            assert resumed.get("question_key") == Q1
            assert resumed.get("attempt_index") == 2
            # Exactly one provider POST: the crashed attempt never got out.
            assert sum(1 for b in bodies if _body_question_key(b) == Q1) == 1

            after = _get_run(physician, run_id)
            assert [s["question_key"] for s in after["sections"]] == [Q1]
            q1_after = next(j for j in after["jobs"] if j["question_key"] == Q1)
            assert q1_after["status"] == "succeeded"
            assert q1_after["attempt_count"] == 2

            # The chain continues with no duplicated sections.
            _drain_with_backoff("s47-s3a", max_steps=15)
            done = _get_run(physician, run_id)
            assert [s["question_key"] for s in done["sections"]] == [Q1, Q2]
            assert sum(1 for b in bodies if _body_question_key(b) == Q2) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S47 slice 3b (RED): reclaimed leases and rotated deployments fence old
# commits (T1/T8).
#
# The adversarial old worker is queue.complete_job itself (S44 precedent:
# test_expired_lease_reclaimed_old_token_cannot_commit calls it directly);
# every assertion reads public GET /runs JSON + captured provider bodies.
#
# RED: queue.begin_attempt does not exist yet (AttributeError on setup).
# The fencing halves already pass via S44 mechanics and are pinned here;
# the final live reclaim initially failed on my +200s jump (claim B's
# deadline runs on the jumped clock, so expiry needs +400s).
# ---------------------------------------------------------------------------


def test_reclaimed_lease_and_rotated_deployment_reject_old_commits() -> None:
    """Old lease tokens and stale deployment generations cannot commit."""
    from datetime import timedelta

    from x_insight.reasoning import queue as queue_module
    from x_insight.reasoning.worker import run_once

    bundle_hash = "synthetic-bundle-hash-s47-slice3b"
    questions = [_make_question(Q1, 1), _make_question(Q2, 2)]
    bodies: list[bytes] = []

    server, thread = _start_provider_always_valid(bodies)
    try:
        host, port = server.server_address
        _insert_bundle("registration", 1, bundle_hash, questions)
        _insert_provider_config(f"http://{host}:{port}")

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s47docF")
            _login(physician, "s47docF", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000475", "s47-s3b-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_id = _start_run(physician, encounter_id, revision, "s47-s3b-run-1")

            claim_a = queue_module.claim_next_job(worker_id="s47-s3b-old")
            assert claim_a is not None
            job_id = str(claim_a["job_id"])
            old_token = str(claim_a["lease_token"])
            old_fencing = int(claim_a["fencing_generation"])

            base = queue_module.now_utc()
            queue_module.set_now_fn(lambda: base + timedelta(seconds=130))
            try:
                claim_b = queue_module.claim_next_job(worker_id="s47-s3b-new")
            finally:
                queue_module.reset_now_fn()
            assert claim_b is not None
            assert str(claim_b["job_id"]) == job_id
            new_token = str(claim_b["lease_token"])
            assert new_token != old_token
            assert int(claim_b["fencing_generation"]) == old_fencing + 1

            # The reclaimed worker's old token can never commit afterwards.
            assert queue_module.complete_job(job_id, old_token, {"ok": True}) is None
            reread = _get_run(physician, run_id)
            held = next(j for j in reread["jobs"] if j["question_key"] == Q1)
            assert held["status"] == "claimed"
            assert reread["sections"] == []

            # A rotated deployment refuses even the current holder's commit.
            current_generation = queue_module.get_deployment_generation()
            queue_module.set_deployment_generation(current_generation + 1)
            try:
                assert (
                    queue_module.complete_job(job_id, new_token, {"ok": True}) is None
                )
                fenced = _get_run(physician, run_id)
                assert (
                    next(j for j in fenced["jobs"] if j["question_key"] == Q1)["status"]
                    == "claimed"
                )
                assert fenced["sections"] == []
            finally:
                queue_module.set_deployment_generation(current_generation)

            # Past the fenced lease, the live generation reclaims and runs.
            live_base = queue_module.now_utc()
            queue_module.set_now_fn(lambda: live_base + timedelta(seconds=400))
            try:
                outcome = run_once(
                    database_url=None,
                    provider_adapter=None,
                    worker_id="s47-s3b-live",
                )
            finally:
                queue_module.reset_now_fn()
            assert outcome.get("claimed") is True
            assert outcome.get("question_key") == Q1
            assert sum(1 for b in bodies if _body_question_key(b) == Q1) == 1
            _drain_with_backoff("s47-s3b", max_steps=15)
            done = _get_run(physician, run_id)
            assert [s["question_key"] for s in done["sections"]] == [Q1, Q2]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S47 slice 4a (RED): mid-flight edit/discard/archive/deactivation refuses
# the late commit (T1/T8).
#
# Plan.md 8.5 archive/discard/deactivation/stale row: "cancel or mark
# ineligible, preserve history, reject late commits and signing". The
# controlled provider blocks inside the outbound request (threaded T8
# run_once); the state change lands while the POST is in flight; the
# worker must then refuse the commit instead of recording a success.
# Edit + discard travel through public routes; archive has no route yet
# (S51 owns it) and deactivation-route session revocation would unusable
# the author's readback, so those two states are set up with one direct
# UPDATE each while every assertion reads public GET JSON + bodies.
#
# RED: no late-commit guard exists, so each scenario records a success
# (thread returns ok, sections [s47_q1]) and the "raised" assertions fail.
# ---------------------------------------------------------------------------


def _start_blocking_provider(bodies: list[bytes], gate: dict):
    """Always-valid CPTs that wait on gate["event"] after capturing a POST."""
    lock = threading.Lock()
    valid_by_key = {
        Q1: _synthetic_cpt_payload(Q1),
        Q2: _synthetic_cpt_payload(Q2),
    }

    def _send(handler, payload: dict) -> None:
        out = json.dumps(payload).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(out)))
        handler.end_headers()
        handler.wfile.write(out)

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            with lock:
                bodies.append(raw)
            gate["event"].wait(30)
            _send(self, valid_by_key.get(_body_question_key(raw), valid_by_key[Q1]))

        def log_message(self, *args) -> None:
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    return server, thread


def _run_once_background(outcomes: list, worker_id: str) -> threading.Thread:
    """Run the public T8 entry on a worker thread; capture ok/raised."""
    from x_insight.reasoning.worker import run_once

    def _target() -> None:
        try:
            outcomes.append(
                (
                    "ok",
                    run_once(
                        database_url=None, provider_adapter=None, worker_id=worker_id
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001 - late-commit refusal surfaces
            outcomes.append(("raised", exc))

    worker = threading.Thread(target=_target)
    worker.daemon = True
    worker.start()
    return worker


def _wait_for_bodies(bodies: list[bytes], count: int, timeout: float = 15.0) -> bool:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(bodies) >= count:
            return True
        time.sleep(0.05)
    return False


def test_midflight_edit_discard_archive_deactivation_refuse_late_commit() -> None:
    """Late success is refused after edit/discard/archive/deactivation."""
    from sqlalchemy import text as sa_text

    from x_insight import db as db_module
    from x_insight.reasoning.coordinator import CoordinatorError

    gate: dict = {"event": threading.Event()}
    gate["event"].set()
    bodies: list[bytes] = []

    server, thread = _start_blocking_provider(bodies, gate)
    try:
        host, port = server.server_address
        _insert_bundle(
            "registration",
            1,
            "synthetic-bundle-hash-s47-slice4a",
            [_make_question(Q1, 1)],
        )
        _insert_provider_config(f"http://{host}:{port}")

        with TestClient(app) as admin, TestClient(app) as _unused_physician:
            _login(admin)
            usernames = ["s47docG1", "s47docG2", "s47docG3", "s47docG4"]
            physicians = []
            for index, username in enumerate(usernames):
                _make_physician(admin, username)
                client = TestClient(app)
                client.__enter__()
                physicians.append(client)
                _login(physicians[-1], username, "secret", "physician")
            try:
                scenarios = [
                    ("edit", "0799000476", "s47-s4a-edit"),
                    ("discard", "0799000477", "s47-s4a-discard"),
                    ("archive", "0799000478", "s47-s4a-archive"),
                    ("deactivate", "0799000479", "s47-s4a-deactivate"),
                ]
                for position, (kind, patient_id, key) in enumerate(scenarios):
                    solo = physicians[position]
                    _patient, encounter = _create_sentinel_patient(
                        solo, patient_id, f"{key}-patient"
                    )
                    encounter_id = encounter["id"]
                    patient_row_id = _patient["id"]
                    saved = solo.patch(
                        f"/api/v1/encounters/{encounter_id}",
                        json={"draft_data": _clinical_draft()},
                        headers=_mutation_headers(solo, revision=encounter["revision"]),
                    )
                    assert saved.status_code == 200
                    revision = _current_revision(solo, encounter_id)
                    run_id = _start_run(solo, encounter_id, revision, f"{key}-run")
                    before = len(bodies)

                    gate["event"].clear()
                    outcomes: list = []
                    worker = _run_once_background(outcomes, f"s47-s4a-{kind}")
                    assert _wait_for_bodies(bodies, before + 1), (
                        f"{kind}: provider never received the in-flight POST"
                    )

                    if kind == "edit":
                        changed = solo.patch(
                            f"/api/v1/encounters/{encounter_id}",
                            json={"draft_data": _mutated_clinical_draft()},
                            headers=_mutation_headers(solo, revision=revision),
                        )
                        assert changed.status_code == 200
                    elif kind == "discard":
                        discarded = solo.post(
                            f"/api/v1/encounters/{encounter_id}/discard",
                            json={"confirm": True},
                            headers=_mutation_headers(solo, revision=revision),
                        )
                        assert discarded.status_code == 200
                    elif kind == "archive":
                        with db_module.transaction() as conn:
                            conn.execute(
                                sa_text(
                                    "UPDATE patients SET archived = TRUE WHERE id = :id"
                                ),
                                {"id": str(patient_row_id)},
                            )
                    else:
                        me = solo.get("/api/v1/me")
                        assert me.status_code == 200
                        deactivated_uid = str(me.json()["id"])
                        with db_module.transaction() as conn:
                            conn.execute(
                                sa_text(
                                    "UPDATE users SET active = FALSE WHERE id = :id"
                                ),
                                {"id": deactivated_uid},
                            )

                    gate["event"].set()
                    worker.join(timeout=60)
                    assert outcomes, f"{kind}: worker thread produced no outcome"
                    if kind == "deactivate":
                        # The refusal already happened; reactivate (by id:
                        # stored usernames are normalized, so raw-name
                        # matching is unreliable) and log back in for
                        # readback (inactive authors hold no session per S03).
                        with db_module.transaction() as conn:
                            conn.execute(
                                sa_text(
                                    "UPDATE users SET active = TRUE WHERE id = :id"
                                ),
                                {"id": deactivated_uid},
                            )
                        relogin = solo.post(
                            "/api/v1/auth/login",
                            json={
                                "username": usernames[position],
                                "password": "secret",
                                "role": "physician",
                            },
                        )
                        assert relogin.status_code == 200
                    status, payload = outcomes[0]
                    # RED: no guard exists, so the late commit succeeds here.
                    assert status == "raised", (
                        f"{kind}: late commit was accepted: {payload!r}"
                    )
                    if kind == "deactivate":
                        # Deactivation is refused at the earliest layer by
                        # design: the adapter's post-POST initial MCP read
                        # hits S41 grant fencing for the inactive actor, so
                        # the S47 late-commit guard is never reached. Both
                        # are honest refusals with the same observable
                        # outcome (failed, no sections).
                        assert isinstance(payload, CoordinatorError) or (
                            "grant denied" in repr(payload).lower()
                        ), (
                            f"{kind}: expected late-commit or grant refusal, "
                            f"got {payload!r}"
                        )
                    else:
                        assert isinstance(payload, CoordinatorError), (
                            f"{kind}: expected late-commit CoordinatorError, "
                            f"got {payload!r}"
                        )

                    body = _get_run(solo, run_id)
                    assert body["sections"] == [], (
                        f"{kind}: refused commit stored a section"
                    )
                    failed = next(j for j in body["jobs"] if j["question_key"] == Q1)
                    assert failed["status"] == "failed"
                    assert body["run"]["status"] == "failed"
                    assert len(bodies) == before + 1

                    if kind == "edit":
                        # Corrected input starts a new run; the old one stays failed.
                        fresh_revision = _current_revision(solo, encounter_id)
                        assert fresh_revision != revision
                        rerun = solo.post(
                            f"/api/v1/encounters/{encounter_id}/runs",
                            json={"encounter_revision": fresh_revision},
                            headers=_mutation_headers(
                                solo,
                                key=f"{key}-rerun",
                                revision=fresh_revision,
                            ),
                        )
                        assert rerun.status_code == 202
                        assert rerun.json()["run_id"] != run_id
                    gate["event"].clear()
                    gate["event"].set()
            finally:
                for client in physicians:
                    client.__exit__(None, None, None)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _make_question_gated(key: str, index: int) -> dict[str, Any]:
    """_make_question plus an honest needs-clarification gate carrier."""
    entry = _make_question(key, index)
    entry["applicability"] = {
        "expression": (
            "encounters.draft_data.history.values.synthetic_flag_true == true"
        ),
        "required_fields": [
            "encounters.draft_data.history.values.synthetic_flag_true",
            "encounters.draft_data.history.values.synthetic_absent_flag",
        ],
        "unknown_policy": "needs_clarification",
    }
    return entry


# ---------------------------------------------------------------------------
# S47 slice 4b (RED): configuration replacement pins a new run; clarification
# never retries blindly and never guesses values (T1/T8).
#
# Replacement is a new provider_configs revision over the same controlled
# localhost URL (one direct INSERT mirroring _insert_provider_config; the
# PUT route itself is S42's tested domain). Clarification uses an honest
# gate carrier: the required synthetic_absent_flag is absent from facts,
# so the run really holds a needs_clarification projection with no job.
#
# RED: replacement does not change the fingerprint (provider revision is
# not pinned), so the second start reuses the first run_id; the retry
# already 409s but the clarification projection half is unpinned.
# ---------------------------------------------------------------------------


def _insert_provider_revision(base_url: str, model: str, revision: int) -> None:
    from x_insight.reasoning.provider_config import encrypt_api_key

    ciphertext = encrypt_api_key(SYNTHETIC_API_KEY)
    with db.transaction() as conn:
        row = (
            conn.execute(
                text(
                    "INSERT INTO provider_configs "
                    "(revision, base_url, model, key_ciphertext, "
                    " key_present, test_status) "
                    "VALUES (:revision, :base_url, :model, :ciphertext, TRUE, "
                    " 'untested') RETURNING id"
                ),
                {
                    "revision": revision,
                    "base_url": base_url,
                    "model": model,
                    "ciphertext": ciphertext,
                },
            )
            .mappings()
            .one()
        )
        conn.execute(
            text(
                "INSERT INTO provider_config_pointer "
                "(id, active_config_id, active_revision) "
                "VALUES (1, :id, :revision) "
                "ON CONFLICT (id) DO UPDATE SET "
                "active_config_id = EXCLUDED.active_config_id, "
                "active_revision = EXCLUDED.active_revision"
            ),
            {"id": str(row["id"]), "revision": revision},
        )


def _drain_success(prefix: str, max_steps: int = 10) -> None:
    """Drive run_once until idle; failures propagate loudly (no backoff)."""
    from x_insight.reasoning.worker import run_once

    for step in range(max_steps):
        outcome = run_once(
            database_url=None,
            provider_adapter=None,
            worker_id=f"{prefix}-{step}",
        )
        if not outcome.get("claimed"):
            return
    raise AssertionError(f"{prefix}: worker did not go idle within {max_steps}")


def test_config_replacement_starts_new_pinned_run() -> None:
    """A replaced provider revision pins a fresh run and stales the old."""
    gate: dict = {"event": threading.Event()}
    gate["event"].set()
    bodies: list[bytes] = []

    server, thread = _start_blocking_provider(bodies, gate)
    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"
        _insert_bundle(
            "registration",
            1,
            "synthetic-bundle-hash-s47-slice4b-config",
            [_make_question(Q1, 1)],
        )
        _insert_provider_config(base_url)

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s47docH")
            _login(physician, "s47docH", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000480", "s47-s4b-config-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_a = _start_run(physician, encounter_id, revision, "s47-s4b-a")
            _drain_success("s47-s4b-a")
            body_a = _get_run(physician, run_id=run_a)
            assert [s["question_key"] for s in body_a["sections"]] == [Q1]

            # Settings repair: same controlled URL, new revision/model.
            _insert_provider_revision(base_url, "synthetic-model-s47-v2", 2)
            run_b = _start_run(physician, encounter_id, revision, "s47-s4b-b")
            # RED: unpinned provider revision reuses run A here.
            assert run_b != run_a
            body_b = _get_run(physician, run_id=run_b)
            assert body_b["fingerprint"] != body_a["fingerprint"]
            assert body_b["run"]["status"] != "succeeded"
            reread_a = _get_run(physician, run_id=run_a)
            assert reread_a["run"]["status"] != "succeeded"
            assert reread_a.get("stale") is True
            assert body_b.get("stale") is False

            # Drain run B under revision 2 so no stale queued job can
            # hijack the in-flight worker below (oldest job claims first).
            _drain_success("s47-s4b-b")
            reread_b = _get_run(physician, run_id=run_b)
            assert [s["question_key"] for s in reread_b["sections"]] == [Q1]

            # An in-flight execution pinned to revision 2 cannot commit
            # after the repair to revision 3.
            _patient2, encounter2 = _create_sentinel_patient(
                physician, "0799000481", "s47-s4b-config-patient-2"
            )
            encounter2_id = encounter2["id"]
            saved2 = physician.patch(
                f"/api/v1/encounters/{encounter2_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter2["revision"]),
            )
            assert saved2.status_code == 200
            revision2 = _current_revision(physician, encounter2_id)
            run_c = _start_run(physician, encounter2_id, revision2, "s47-s4b-c")
            before = len(bodies)
            gate["event"].clear()
            outcomes: list = []
            worker = _run_once_background(outcomes, "s47-s4b-inflight")
            assert _wait_for_bodies(bodies, before + 1), "in-flight POST never arrived"
            _insert_provider_revision(base_url, "synthetic-model-s47-v3", 3)
            gate["event"].set()
            worker.join(timeout=60)
            assert outcomes
            assert outcomes[0][0] == "raised", (
                f"post-replacement late commit accepted: {outcomes[0][1]!r}"
            )
            body_c = _get_run(physician, run_id=run_c)
            assert body_c["sections"] == []
            assert body_c["run"]["status"] == "failed"
            gate["event"].set()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_clarification_never_retries_or_guesses() -> None:
    """A needs-clarification question gets no POSTs, no retry, no values."""
    bodies: list[bytes] = []

    server, thread = _start_provider_always_valid(bodies)
    try:
        host, port = server.server_address
        _insert_bundle(
            "registration",
            1,
            "synthetic-bundle-hash-s47-slice4b-clarify",
            [_make_question(Q1, 1), _make_question_gated(Q2, 2)],
        )
        _insert_provider_config(f"http://{host}:{port}")

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s47docI")
            _login(physician, "s47docI", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000482", "s47-s4b-clarify-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_id = _start_run(physician, encounter_id, revision, "s47-s4b-cl")
            _drain_success("s47-s4b-cl")

            body = _get_run(physician, run_id)
            assert [s["question_key"] for s in body["sections"]] == [Q1]
            assert sum(1 for b in bodies if _body_question_key(b) == Q2) == 0
            assert body["run"]["status"] == "needs_clarification"
            assert body.get("proposal") is None
            projections = {p["question_key"]: p for p in body["projections"]}
            assert projections[Q2]["applicability"] == "needs_clarification"
            assert "synthetic_absent_flag" in projections[Q2]["applicability_reason"]

            # Blind retry of the clarification question is refused.
            retry = physician.post(
                f"/api/v1/runs/{run_id}/retry",
                json={
                    "question_key": Q2,
                    "failed_stage": "estimating_cpts",
                    "expected_run_revision": int(body["run"]["revision"]),
                },
                headers=_mutation_headers(physician, key="s47-s4b-cl-retry"),
            )
            assert retry.status_code == 409
            reread = _get_run(physician, run_id)
            assert [s["question_key"] for s in reread["sections"]] == [Q1]
            assert sum(1 for b in bodies if _body_question_key(b) == Q2) == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
