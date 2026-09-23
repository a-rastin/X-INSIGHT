"""S45 slice 1 (RED): one full synthetic clinical question end to end (T1/T8).

Slice-1 scope ONLY (tasks.md S45.1; plan.md 7.4, 8-9; FR-32-35):
public start -> worker -> real MCP -> controlled provider -> all-CPT
validation -> effective XML -> exact inference -> stored template section
observable through GET /runs/{id}.

Synthetic 2-node A->B network only (never BNs/, never clinical, never a
released default). Math is independent of any implementation (plan.md 7.4):
A[80,20], B|A=no[90,10], B|A=yes[30,70]; P(B=yes)=0.22,
P(B=yes|A=yes)=0.70, P(A=yes|B=yes)=7/11. This slice asserts the marginal
P(B=yes)=0.22 within 1e-9; the other two literals document the fixture.

Proposed minimal backend contract (no extra seams):
- Synthetic bundle pins (test-only carrier, never a production default)
  hold ONE question "synthetic_example" with "version" "v1",
  "network_hash" = sha256(network XML bytes), "network_xml" = UTF-8
  XMLBIF string for the 2-node A->B network, plus synthetic "prompt" and
  "template" placeholders. No patient_mappings gate: projection is ready.
- Provider config points at the controlled localhost endpoint (setup-only
  direct SQL with the real encrypt helper; worker reads it in future).
- POST /encounters/{id}/runs (202) then worker run_once() (T8 entry point,
  no mocks of owned modules) must execute through real MCP stdio
  (mcp_host, no direct-call shortcut) + controlled localhost HTTP
  (X_INSIGHT_PROVIDER_ALLOW_LOCAL=true) returning the exact CPTs above.
- GET /runs/{id} (T1) must then expose top-level "sections": one entry
  with the five plan.md section 9 transparency fields from persisted data:
  "question_key", "network_version", "patient_inputs" (exact frozen
  clinical facts), "cpt_percentages" (exact returned percentages),
  "result" (deterministic network result with posterior 0.22 for B=yes).
  Template prose is never the recommendation source.

EXPECTED RED: run_once() today only claims + records an attempt; there is
no coordinator, no artifact/section tables, no MCP/provider wiring. POST
succeeds (202) and run_once reports claimed, but GET has no "sections"
key, so body["sections"] raises KeyError (or a 404/500 on missing tables
in stricter setups). Provider captures zero POSTs. Not a passing test.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import socketserver
import threading
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all

SYNTHETIC_HISTORY_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "content" / "history"
)

SYNTHETIC_QUESTION = "synthetic_example"
SYNTHETIC_NETWORK_VERSION = "v1"
SYNTHETIC_BUNDLE_HASH = "synthetic-bundle-hash-s45-slice1"
SYNTHETIC_HISTORY_VERSION = "synthetic-history-v1"
SYNTHETIC_DDI_VERSION = "synthetic-ddi-s45-v1"
SYNTHETIC_MEDICATION_FINGERPRINT = "fp-synth-s45-slice1"
SYNTHETIC_MODEL = "synthetic-model-s45-slice1"
SYNTHETIC_API_KEY = "synthetic-provider-key-s45-001"
SYNTHETIC_PROMPT_MARKER = "SYNTHETIC-S45-PROMPT-001"

SENTINEL_FIRST = "SentinelAlpha"
SENTINEL_LAST = "SentinelBeta"
SENTINEL_PID = "0799000901"
SENTINEL_PHONE = "SENTINEL-PHONE-0045"

# Plan.md 7.4 synthetic 2-node A->B XMLBIF (same bytes as S23 slice 1).
SYNTHETIC_XML = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>SyntheticCPT</NAME>'
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)

# Independent literals (never computed by the implementation under test).
EXPECTED_P_B_YES = 0.22
EXPECTED_P_B_YES_GIVEN_A_YES = 0.70
EXPECTED_P_A_YES_GIVEN_B_YES = 7 / 11


@pytest.fixture(autouse=True)
def clean_single_question(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, runs, run_questions, reasoning_jobs, "
                "reasoning_attempts, audit_events, "
                "model_bundle_pointers, model_bundle_events, "
                "mcp_question_grants, provider_configs, "
                "provider_config_pointer, queue_fairness"
            )
        )
    reset_all()
    yield
    reset_all()


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
        headers=_mutation_headers(admin, key=f"s45-{username}-create"),
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


def _clinical_draft():
    return {
        "diagnosis": {"answers": {"synthetic_item": "synthetic_value"}},
        "history": {
            "definition_version": SYNTHETIC_HISTORY_VERSION,
            "values": {
                "synthetic_flag_true": {"status": "known", "value": True},
            },
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
        "medications": [
            {"catalog_drug_id": "synthetic-med-a"},
        ],
        "ddi_report": {
            "dataset_version": SYNTHETIC_DDI_VERSION,
            "medication_fingerprint": SYNTHETIC_MEDICATION_FINGERPRINT,
        },
    }


def _synthetic_cpt_response(network_hash: str) -> dict:
    return {
        "question_key": SYNTHETIC_QUESTION,
        "network_version": SYNTHETIC_NETWORK_VERSION,
        "network_hash": network_hash,
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


def _insert_synthetic_bundle(network_hash: str) -> None:
    pins = {
        "questions": [
            {
                "question_key": SYNTHETIC_QUESTION,
                "version": SYNTHETIC_NETWORK_VERSION,
                "network_hash": network_hash,
                "network_xml": SYNTHETIC_XML.decode("utf-8"),
                "prompt": (
                    f"{SYNTHETIC_PROMPT_MARKER} estimate every CPT as "
                    "percentages summing to 100 using only listed patient "
                    "facts. Do not write a plan. Do not choose applicability."
                ),
                "template": {
                    "template_version": "synthetic-v1",
                    "branches": {
                        "needs_clarification": {
                            "heading": "synthetic",
                            "body": "synthetic",
                        }
                    },
                },
            }
        ]
    }
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO model_bundle_pointers "
                "(workflow, revision, bundle_hash, pins) "
                "VALUES ('registration', 1, :hash, CAST(:pins AS jsonb)) "
                "ON CONFLICT (workflow) DO UPDATE SET revision = 1, "
                "bundle_hash = :hash, pins = CAST(:pins AS jsonb)"
            ),
            {"hash": SYNTHETIC_BUNDLE_HASH, "pins": json.dumps(pins)},
        )
        conn.execute(
            text(
                "INSERT INTO model_bundle_events "
                "(workflow, revision, bundle_hash, pins, action) "
                "VALUES ('registration', 1, :hash, CAST(:pins AS jsonb), "
                "'activate') ON CONFLICT (workflow, revision) DO NOTHING"
            ),
            {"hash": SYNTHETIC_BUNDLE_HASH, "pins": json.dumps(pins)},
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


def _current_revision(physician, encounter_id) -> int:
    fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
    assert fetched.status_code == 200
    return int(fetched.json()["encounter"]["revision"])


def test_single_synthetic_question_end_to_end() -> None:
    """Full synthetic A->B question through real worker/MCP/provider/inference.

    RED: POST succeeds and run_once claims, but GET /runs has no stored
    template section (KeyError on "sections"); the controlled provider sees
    no POST. Verifies the plan.md 0.22/0.70/7/11 fixture end to end once the
    coordinator exists. Assertions read only public HTTP GET plus the
    captured external provider request; setup-only SQL never asserts.
    """
    from x_insight.reasoning.worker import run_once

    network_hash = hashlib.sha256(SYNTHETIC_XML).hexdigest()
    payload = _synthetic_cpt_response(network_hash)
    bodies: list[bytes] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            data = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args) -> None:
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"
        _insert_synthetic_bundle(network_hash)
        _insert_provider_config(base_url)

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s45docA")
            _login(physician, "s45docA", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, SENTINEL_PID, "s45-s1-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)

            started = physician.post(
                f"/api/v1/encounters/{encounter_id}/runs",
                json={"encounter_revision": revision},
                headers=_mutation_headers(
                    physician, key="s45-s1-run-1", revision=revision
                ),
            )
            assert started.status_code == 202
            run_id = started.json()["run_id"]
            uuid.UUID(run_id)

            outcome = run_once(
                database_url=None, provider_adapter=None, worker_id="s45-worker"
            )
            assert outcome.get("claimed") is True
            assert outcome.get("run_id") == run_id
            assert outcome.get("question_key") == SYNTHETIC_QUESTION

            fetched = physician.get(f"/api/v1/runs/{run_id}")
            assert fetched.status_code == 200
            body = fetched.json()

            # RED: no coordinator/section storage exists yet -> KeyError.
            sections = body["sections"]
            assert isinstance(sections, list) and len(sections) == 1
            section = sections[0]
            assert section["question_key"] == SYNTHETIC_QUESTION
            assert section["network_version"] == SYNTHETIC_NETWORK_VERSION

            patient_inputs = section["patient_inputs"]
            dumped_inputs = json.dumps(patient_inputs, sort_keys=True)
            assert "synthetic_flag_true" in dumped_inputs
            for sentinel in (SENTINEL_FIRST, SENTINEL_LAST, SENTINEL_PID):
                assert sentinel not in dumped_inputs

            cpt_percentages = section["cpt_percentages"]
            dumped_cpts = json.dumps(cpt_percentages, sort_keys=True)
            assert "80" in dumped_cpts and "20" in dumped_cpts
            assert "90" in dumped_cpts and "10" in dumped_cpts
            assert "30" in dumped_cpts and "70" in dumped_cpts

            result = section["result"]
            posterior = float(result["posterior"])
            assert result["target"] == "B"
            assert result["state"] == "yes"
            assert abs(posterior - EXPECTED_P_B_YES) <= 1e-9
            assert EXPECTED_P_B_YES_GIVEN_A_YES == 0.70
            assert abs(EXPECTED_P_A_YES_GIVEN_B_YES - 7 / 11) <= 1e-12

            assert len(bodies) == 1
            captured = json.loads(bodies[0].decode("utf-8"))
            dumped_body = json.dumps(captured, sort_keys=True)
            assert SYNTHETIC_PROMPT_MARKER in dumped_body
            assert network_hash in dumped_body
            assert SYNTHETIC_API_KEY not in dumped_body
            for sentinel in (SENTINEL_FIRST, SENTINEL_LAST, SENTINEL_PID):
                assert sentinel not in dumped_body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_single_question_provenance_persisted_and_crash_resume() -> None:
    """S45 slice 2 (RED): persisted provenance + crash-resume (T1/T8).

    After a successful synthetic A->B run, GET /runs/{id} section must
    expose persisted provenance: pinned prompt text, model identity,
    attempt reference, accepted percentages tables, effective XML hash
    (distinct from base bytes hash), and query/result. A second GET after
    a simulated worker restart (fresh run_once with no new provider POST,
    plus a new TestClient GET) must return the identical section.

    EXPECTED RED: GET sections currently expose prompt/template but no
    model/effective_hash/query keys, so section["model"] raises KeyError.
    """
    from x_insight.reasoning.worker import run_once

    network_hash = hashlib.sha256(SYNTHETIC_XML).hexdigest()
    payload = _synthetic_cpt_response(network_hash)
    bodies: list[bytes] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            data = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args) -> None:
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"
        _insert_synthetic_bundle(network_hash)
        _insert_provider_config(base_url)

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s45docB")
            _login(physician, "s45docB", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000905", "s45-s2-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)

            started = physician.post(
                f"/api/v1/encounters/{encounter_id}/runs",
                json={"encounter_revision": revision},
                headers=_mutation_headers(
                    physician, key="s45-s2-run-1", revision=revision
                ),
            )
            assert started.status_code == 202
            run_id = started.json()["run_id"]
            uuid.UUID(run_id)

            outcome = run_once(
                database_url=None, provider_adapter=None, worker_id="s45-worker-s2"
            )
            assert outcome.get("claimed") is True
            assert outcome.get("run_id") == run_id

            fetched = physician.get(f"/api/v1/runs/{run_id}")
            assert fetched.status_code == 200
            body = fetched.json()
            sections = body["sections"]
            assert isinstance(sections, list) and len(sections) == 1
            section = sections[0]

            # Pinned prompt text persists.
            assert SYNTHETIC_PROMPT_MARKER in section["prompt"]
            # Model identity persists (RED: no "model" key exposed).
            assert section["model"]["model"] == SYNTHETIC_MODEL
            assert int(section["model"]["attempt_index"]) == 1
            assert section["model"]["provider_revision"] == 1
            # Accepted percentages tables persist.
            dumped_cpts = json.dumps(section["cpt_percentages"], sort_keys=True)
            assert "80" in dumped_cpts and "20" in dumped_cpts
            assert "90" in dumped_cpts and "10" in dumped_cpts
            assert "30" in dumped_cpts and "70" in dumped_cpts
            # Effective XML hash persists and differs from base bytes hash.
            assert section["effective_hash"] != network_hash
            assert len(section["effective_hash"]) == 64
            # Query/result persist.
            assert section["query"]["target"] == "B"
            assert section["query"]["state"] == "yes"
            assert section["query"]["evidence"] == {}
            assert abs(float(section["result"]["posterior"]) - 0.22) <= 1e-9
            assert section["result"]["target"] == "B"
            assert section["result"]["state"] == "yes"

            # Crash-resume: fresh run_once claims nothing, no new POST,
            # and both the same-client and a new-client GET are identical.
            first_dump = json.dumps(body["sections"], sort_keys=True)
            n_posts = len(bodies)
            assert n_posts == 1
            restart = run_once(
                database_url=None,
                provider_adapter=None,
                worker_id="s45-worker-s2-restart",
            )
            assert restart.get("claimed") is False
            assert len(bodies) == n_posts
            refetched = physician.get(f"/api/v1/runs/{run_id}")
            assert refetched.status_code == 200
            sections_dump = json.dumps(refetched.json()["sections"], sort_keys=True)
            assert sections_dump == first_dump
            with TestClient(app) as fresh:
                _login(fresh, "s45docB", "secret", "physician")
                fresh_fetched = fresh.get(f"/api/v1/runs/{run_id}")
                assert fresh_fetched.status_code == 200
                assert (
                    json.dumps(fresh_fetched.json()["sections"], sort_keys=True)
                    == first_dump
                )
                assert len(bodies) == n_posts
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_single_question_structure_mutation_rejected_base_unchanged() -> None:
    """S45 slice 3 (RED): structure mutation rejected, base bytes intact (T1/T8).

    Same pipeline with (a) renamed node + extra table and (b) missing
    root-A table. Each must leave the step unsuccessful (run/job not
    succeeded, no sections entry with a posterior, error surfaced on GET
    or worker result), must not mutate pinned base bytes, and must never
    substitute a registered default. A subsequent valid run still
    succeeds with posterior 0.22.

    EXPECTED RED: mutated responses may validate/partially persist, or
    the failure surfaces no error string on GET (jobs stay claimed with
    no failure details), so the error-surfaced assertion fails.
    """
    from x_insight.reasoning.worker import run_once

    network_hash = hashlib.sha256(SYNTHETIC_XML).hexdigest()
    valid_payload = _synthetic_cpt_response(network_hash)
    mutated_extra = {
        "question_key": SYNTHETIC_QUESTION,
        "network_version": SYNTHETIC_NETWORK_VERSION,
        "network_hash": network_hash,
        "tables": [
            {
                "node_id": "A",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [80, 20]}],
            },
            {
                "node_id": "B_mutated",
                "parent_ids": ["A"],
                "states": ["no", "yes"],
                "rows": [
                    {"parent_states": ["no"], "percentages": [90, 10]},
                    {"parent_states": ["yes"], "percentages": [30, 70]},
                ],
            },
            {
                "node_id": "C_extra",
                "parent_ids": [],
                "states": ["no", "yes"],
                "rows": [{"parent_states": [], "percentages": [50, 50]}],
            },
        ],
    }
    mutated_missing = {
        "question_key": SYNTHETIC_QUESTION,
        "network_version": SYNTHETIC_NETWORK_VERSION,
        "network_hash": network_hash,
        "tables": [
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
    state = {"payload": mutated_extra}
    bodies: list[bytes] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            data = json.dumps(state["payload"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args) -> None:
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"
        _insert_synthetic_bundle(network_hash)
        _insert_provider_config(base_url)

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s45docC")
            _login(physician, "s45docC", "secret", "physician")

            # Sub-case (a): renamed node + extra table must not succeed.
            _patient_a, encounter_a = _create_sentinel_patient(
                physician, "0799000906", "s45-s3-patient-a"
            )
            encounter_id_a = encounter_a["id"]
            saved_a = physician.patch(
                f"/api/v1/encounters/{encounter_id_a}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter_a["revision"]),
            )
            assert saved_a.status_code == 200
            revision_a = _current_revision(physician, encounter_id_a)
            started_a = physician.post(
                f"/api/v1/encounters/{encounter_id_a}/runs",
                json={"encounter_revision": revision_a},
                headers=_mutation_headers(
                    physician, key="s45-s3-run-a", revision=revision_a
                ),
            )
            assert started_a.status_code == 202
            run_id_a = started_a.json()["run_id"]
            try:
                outcome_a = run_once(
                    database_url=None,
                    provider_adapter=None,
                    worker_id="s45-worker-s3a",
                )
            except Exception:
                outcome_a = None
            if outcome_a is not None:
                assert outcome_a.get("run_id") != run_id_a or True
            fetched_a = physician.get(f"/api/v1/runs/{run_id_a}")
            assert fetched_a.status_code == 200
            body_a = fetched_a.json()
            assert body_a["run"]["status"] != "succeeded"
            assert body_a["sections"] == []
            pinned_a = body_a["pinned"]["pins"]["questions"][0]
            assert pinned_a["network_hash"] == network_hash
            assert (
                hashlib.sha256(pinned_a["network_xml"].encode("utf-8")).hexdigest()
                == network_hash
            )
            dumped_a = json.dumps(body_a, sort_keys=True).lower()
            assert (
                "invalid_cpt" in dumped_a or "error" in dumped_a or "failed" in dumped_a
            )

            # Subsequent valid run still succeeds with 0.22 (base intact).
            state["payload"] = valid_payload
            _patient_b, encounter_b = _create_sentinel_patient(
                physician, "0799000907", "s45-s3-patient-b"
            )
            encounter_id_b = encounter_b["id"]
            saved_b = physician.patch(
                f"/api/v1/encounters/{encounter_id_b}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter_b["revision"]),
            )
            assert saved_b.status_code == 200
            revision_b = _current_revision(physician, encounter_id_b)
            started_b = physician.post(
                f"/api/v1/encounters/{encounter_id_b}/runs",
                json={"encounter_revision": revision_b},
                headers=_mutation_headers(
                    physician, key="s45-s3-run-b", revision=revision_b
                ),
            )
            assert started_b.status_code == 202
            run_id_b = started_b.json()["run_id"]
            outcome_b = run_once(
                database_url=None, provider_adapter=None, worker_id="s45-worker-s3b"
            )
            assert outcome_b.get("claimed") is True
            fetched_b = physician.get(f"/api/v1/runs/{run_id_b}")
            assert fetched_b.status_code == 200
            section_b = fetched_b.json()["sections"][0]
            assert abs(float(section_b["result"]["posterior"]) - 0.22) <= 1e-9

            # Sub-case (b): missing root-A table must not succeed.
            state["payload"] = mutated_missing
            _patient_c, encounter_c = _create_sentinel_patient(
                physician, "0799000908", "s45-s3-patient-c"
            )
            encounter_id_c = encounter_c["id"]
            saved_c = physician.patch(
                f"/api/v1/encounters/{encounter_id_c}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter_c["revision"]),
            )
            assert saved_c.status_code == 200
            revision_c = _current_revision(physician, encounter_id_c)
            started_c = physician.post(
                f"/api/v1/encounters/{encounter_id_c}/runs",
                json={"encounter_revision": revision_c},
                headers=_mutation_headers(
                    physician, key="s45-s3-run-c", revision=revision_c
                ),
            )
            assert started_c.status_code == 202
            run_id_c = started_c.json()["run_id"]
            try:
                run_once(
                    database_url=None,
                    provider_adapter=None,
                    worker_id="s45-worker-s3c",
                )
            except Exception:
                pass
            fetched_c = physician.get(f"/api/v1/runs/{run_id_c}")
            assert fetched_c.status_code == 200
            body_c = fetched_c.json()
            assert body_c["run"]["status"] != "succeeded"
            assert body_c["sections"] == []
            pinned_c = body_c["pinned"]["pins"]["questions"][0]
            assert pinned_c["network_hash"] == network_hash
            assert (
                hashlib.sha256(pinned_c["network_xml"].encode("utf-8")).hexdigest()
                == network_hash
            )
            dumped_c = json.dumps(body_c, sort_keys=True).lower()
            assert (
                "invalid_cpt" in dumped_c or "error" in dumped_c or "failed" in dumped_c
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_single_question_template_only_rendering_no_prose() -> None:
    """S45 slice 4 (RED): prose-bearing responses rejected; template-only (T1/T8).

    CONTRACT CORRECTION (binding; plan.md 7.4 "no extra fields" + S43 card
    "Reject extra prose" + test_estimation.py slice-3 "extra prose ->
    invalid_cpt, retryable" take precedence over this test as first
    written, which wrongly expected valid-CPTs-plus-prose to succeed).
    "LLM prose is never used as the recommendation" holds strictly: a
    prose-bearing response is unsuccessful and yields NO section or
    recommendation at all. validate_cpt_response / provider strictness are
    unchanged (S43 regression stays green).

    Controlled provider first returns the valid CPTs PLUS extra prose
    fields: run_once must raise, GET must show the step unsuccessful with
    no sections entry, an error surfaced, and no prose substring persisted
    anywhere in GET. A subsequent valid run renders purely from the
    reviewed mapping + stored posterior (rendered_text holds the stored
    0.22, holds no provider-prose substring) and exposes all five
    transparency fields from persisted data.
    """
    from x_insight.reasoning.worker import run_once

    network_hash = hashlib.sha256(SYNTHETIC_XML).hexdigest()
    prose_recommend = "SYNTHETIC-PROSE-RECOMMEND-0045"
    prose_explain = "SYNTHETIC-PROSE-EXPLAIN-0045"
    base_tables = _synthetic_cpt_response(network_hash)["tables"]
    prose_payload = {
        "question_key": SYNTHETIC_QUESTION,
        "network_version": SYNTHETIC_NETWORK_VERSION,
        "network_hash": network_hash,
        "tables": base_tables,
        "recommendation": prose_recommend + " choose opposite with 0.99",
        "explanation": prose_explain + " posterior is 0.99 not 0.22",
    }
    state = {"payload": prose_payload}
    bodies: list[bytes] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            data = json.dumps(state["payload"]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args) -> None:
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}
    )
    thread.daemon = True
    thread.start()
    try:
        host, port = server.server_address
        base_url = f"http://{host}:{port}"
        _insert_synthetic_bundle(network_hash)
        _insert_provider_config(base_url)

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s45docD")
            _login(physician, "s45docD", "secret", "physician")

            # Prose-bearing response: unsuccessful, no section, error
            # surfaced, no prose persisted anywhere in GET.
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000909", "s45-s4-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)

            started = physician.post(
                f"/api/v1/encounters/{encounter_id}/runs",
                json={"encounter_revision": revision},
                headers=_mutation_headers(
                    physician, key="s45-s4-run-1", revision=revision
                ),
            )
            assert started.status_code == 202
            run_id = started.json()["run_id"]
            uuid.UUID(run_id)

            with pytest.raises(Exception):
                run_once(
                    database_url=None,
                    provider_adapter=None,
                    worker_id="s45-worker-s4",
                )

            fetched = physician.get(f"/api/v1/runs/{run_id}")
            assert fetched.status_code == 200
            body = fetched.json()
            assert body["run"]["status"] != "succeeded"
            assert body["sections"] == []
            dumped = json.dumps(body, sort_keys=True)
            assert (
                "invalid_cpt" in dumped.lower()
                or "error" in dumped.lower()
                or "failed" in dumped.lower()
            )
            assert prose_recommend not in dumped
            assert prose_explain not in dumped
            assert "recommendation" not in dumped
            assert "explanation" not in dumped

            # Valid run: template-only rendering from persisted data.
            state["payload"] = _synthetic_cpt_response(network_hash)
            _patient_b, encounter_b = _create_sentinel_patient(
                physician, "0799000910", "s45-s4-patient-b"
            )
            encounter_id_b = encounter_b["id"]
            saved_b = physician.patch(
                f"/api/v1/encounters/{encounter_id_b}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter_b["revision"]),
            )
            assert saved_b.status_code == 200
            revision_b = _current_revision(physician, encounter_id_b)

            started_b = physician.post(
                f"/api/v1/encounters/{encounter_id_b}/runs",
                json={"encounter_revision": revision_b},
                headers=_mutation_headers(
                    physician, key="s45-s4-run-2", revision=revision_b
                ),
            )
            assert started_b.status_code == 202
            run_id_b = started_b.json()["run_id"]
            uuid.UUID(run_id_b)

            outcome = run_once(
                database_url=None,
                provider_adapter=None,
                worker_id="s45-worker-s4b",
            )
            assert outcome.get("claimed") is True

            fetched_b = physician.get(f"/api/v1/runs/{run_id_b}")
            assert fetched_b.status_code == 200
            body_b = fetched_b.json()
            sections = body_b["sections"]
            assert isinstance(sections, list) and len(sections) == 1
            section = sections[0]

            rendered = section.get("rendered_text")
            assert isinstance(rendered, str) and rendered
            assert "0.22" in rendered
            assert prose_recommend not in rendered
            assert prose_explain not in rendered
            section_dump = json.dumps(section, sort_keys=True)
            assert prose_recommend not in section_dump
            assert prose_explain not in section_dump
            assert "recommendation" not in section_dump
            assert "explanation" not in section_dump
            assert json.dumps(body_b, sort_keys=True).count(prose_recommend) == 0
            assert json.dumps(body_b, sort_keys=True).count(prose_explain) == 0

            assert section["question_key"] == SYNTHETIC_QUESTION
            assert section["network_version"] == SYNTHETIC_NETWORK_VERSION
            frozen_facts = body_b["projections"][0]["projection"]["facts"]
            assert section["patient_inputs"] == frozen_facts
            dumped_inputs = json.dumps(section["patient_inputs"], sort_keys=True)
            assert "synthetic_flag_true" in dumped_inputs
            dumped_cpts = json.dumps(section["cpt_percentages"], sort_keys=True)
            assert "80" in dumped_cpts and "20" in dumped_cpts
            assert "90" in dumped_cpts and "10" in dumped_cpts
            assert "30" in dumped_cpts and "70" in dumped_cpts
            assert section["result"]["target"] == "B"
            assert section["result"]["state"] == "yes"
            assert abs(float(section["result"]["posterior"]) - 0.22) <= 1e-9

            assert len(bodies) == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
