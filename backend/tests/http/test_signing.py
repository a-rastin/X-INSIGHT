"""S49 slice 1 (RED): secondary-plan save + sign current successful run (T1).

Scope: plan.md 4.3/9; tasks.md S49.1; FR-15/FR-22. Seam T1 only
(authenticated HTTP against real PostgreSQL).

Proposed minimal contract under test (no signing routes exist yet, so
every secondary-plan/sign assertion below currently fails with 404):
- PATCH /api/v1/encounters/{id}/secondary-plan with {"text": ...} plus
  CSRF + Idempotency-Key + If-Match (expected secondary-plan revision,
  "0" for the first save) persists revisioned physician text (200,
  revision 1, then revision 2 on edit).
- GET /api/v1/encounters/{id}/secondary-plan exposes the current text
  plus a revision history containing both saved texts.
- GET /api/v1/runs/{run_id} proposal (immutable initial proposal) is
  byte-identical before/after secondary-plan saves; secondary text
  never leaks into it.
- POST /api/v1/encounters/{id}/sign with {encounter_revision, run_id,
  secondary_plan_revision, review_acknowledgments,
  baseline_acknowledgment} plus CSRF + Idempotency-Key (+ If-Match =
  encounter_revision) succeeds (200/201, state signed) when the run is
  succeeded, the fingerprint is current, and all revisions/acks are
  current. Server recomputes eligibility; client flags never grant it.

Setup uses a REAL completed synthetic pipeline result: a one-question
synthetic bundle (same 2-node A->B bytes as S45/S46, never BNs/, never
clinical), a controlled localhost provider
(X_INSIGHT_PROVIDER_ALLOW_LOCAL=true), a synthetic DDI release, and the
real worker entry point drained to succeeded. No signable success flag
is ever forged via direct SQL UPDATE of runs; SQL is setup-only
(bundles/provider/DDI rows). Synthetic values only.
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
from x_insight.contracts import content_hash
from x_insight.ddi.terminology import canonical_pair_key
from x_insight.identity.throttle import reset_all

SYNTHETIC_HISTORY_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "content" / "history"
)

SYNTHETIC_QUESTION = "s49_single"
SYNTHETIC_NETWORK_VERSION = "v1"
SYNTHETIC_BUNDLE_HASH = "synthetic-bundle-hash-s49-slice1"
SYNTHETIC_HISTORY_VERSION = "synthetic-history-v1"
SYNTHETIC_DDI_VERSION = "synthetic-ddi-s49"
SYNTHETIC_MODEL = "synthetic-model-s49"
SYNTHETIC_API_KEY = "synthetic-provider-key-s49-001"

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

MED_A = "synthetic-s49-med-a"
MED_B = "synthetic-s49-med-b"

SECONDARY_V1 = "SYNTHETIC-S49-SECONDARY-v1-test-only"
SECONDARY_V2 = "SYNTHETIC-S49-SECONDARY-v2-revised-test-only"


@pytest.fixture(autouse=True)
def clean_signing(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")
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
    reset_all()
    yield
    reset_all()


def login(client, username="admin", password="admin", role="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200
    return response.json()


def mutation_headers(client, key=None, revision=None):
    headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
    if key is not None:
        headers["Idempotency-Key"] = key
    if revision is not None:
        headers["If-Match"] = str(revision)
    return headers


def create_physician(admin, username, key):
    created = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "secret"},
        headers=mutation_headers(admin, key),
    )
    assert created.status_code == 201


def create_patient(physician, patient_id, key):
    body = {
        "first_name": "Anna",
        "last_name": "Muller",
        "sex": "F",
        "age": 30,
        "patient_id": patient_id,
        "clinical_status": "first_time",
    }
    response = physician.post(
        "/api/v1/patients", json=body, headers=mutation_headers(physician, key)
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["patient"], payload["encounter"]


def current_revision(physician, encounter_id) -> int:
    fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
    assert fetched.status_code == 200
    return int(fetched.json()["encounter"]["revision"])


def clinical_draft(medications, ddi_version, ddi_fingerprint) -> dict:
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
        "medications": medications,
        "ddi_report": {
            "dataset_version": ddi_version,
            "medication_fingerprint": ddi_fingerprint,
        },
    }


def synthetic_cpt_payload(question_key: str) -> dict:
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


def insert_bundle_for(workflow: str, bundle_hash: str) -> None:
    pins = {
        "questions": [
            {
                "question_key": SYNTHETIC_QUESTION,
                "version": SYNTHETIC_NETWORK_VERSION,
                "network_hash": NETWORK_HASH,
                "network_xml": SYNTHETIC_XML.decode("utf-8"),
                "prompt": (
                    f"SYNTH-S49-{SYNTHETIC_QUESTION} estimate every CPT as "
                    "percentages summing to 100 using only listed patient "
                    "facts. Do not write a plan. Do not choose applicability."
                ),
                "template": {"template_version": "synthetic-v1"},
            }
        ]
    }
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO model_bundle_pointers "
                "(workflow, revision, bundle_hash, pins) "
                "VALUES (:workflow, 1, :hash, CAST(:pins AS jsonb)) "
                "ON CONFLICT (workflow) DO UPDATE SET revision = 1, "
                "bundle_hash = :hash, pins = CAST(:pins AS jsonb)"
            ),
            {"workflow": workflow, "hash": bundle_hash, "pins": json.dumps(pins)},
        )
        conn.execute(
            text(
                "INSERT INTO model_bundle_events "
                "(workflow, revision, bundle_hash, pins, action) "
                "VALUES (:workflow, 1, :hash, CAST(:pins AS jsonb), "
                "'activate') ON CONFLICT (workflow, revision) DO NOTHING"
            ),
            {"workflow": workflow, "hash": bundle_hash, "pins": json.dumps(pins)},
        )


def insert_bundle() -> None:
    insert_bundle_for("registration", SYNTHETIC_BUNDLE_HASH)


def insert_provider_config(base_url: str) -> None:
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


def insert_ddi_release(version: str, evidence: list[dict]) -> None:
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO ddi_dataset_releases "
                "(version, dataset_hash, source_inventory, "
                "terminology_provenance, review_record, corrections, "
                "coverage, evidence) "
                "VALUES (:version, :dataset_hash, "
                "CAST(:source_inventory AS JSONB), "
                "CAST(:terminology_provenance AS JSONB), "
                "CAST(:review_record AS JSONB), "
                "CAST(:corrections AS JSONB), "
                "CAST(:coverage AS JSONB), "
                "CAST(:evidence AS JSONB))"
            ),
            {
                "version": version,
                "dataset_hash": f"synthetic-hash-{version}",
                "source_inventory": json.dumps([]),
                "terminology_provenance": json.dumps(None),
                "review_record": json.dumps(
                    {"synthetic_fixture": True, "reviewer": "dr-synthetic"}
                ),
                "corrections": json.dumps([]),
                "coverage": json.dumps({"scope": "limited", "exclusions": []}),
                "evidence": json.dumps(evidence),
            },
        )


def start_provider(payload: dict, bodies: list[bytes]):
    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            out = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

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


def drain(worker_prefix: str, max_steps: int = 10) -> list[dict]:
    from x_insight.reasoning.worker import run_once as _real_run_once

    outcomes: list[dict] = []
    for step in range(max_steps):
        outcome = _real_run_once(
            database_url=None,
            provider_adapter=None,
            worker_id=f"{worker_prefix}-{step}",
        )
        outcomes.append(outcome)
        if not outcome.get("claimed"):
            break
    return outcomes


def start_run(physician, encounter_id, revision, key: str) -> str:
    started = physician.post(
        f"/api/v1/encounters/{encounter_id}/runs",
        json={"encounter_revision": revision},
        headers=mutation_headers(physician, key=key, revision=revision),
    )
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    uuid.UUID(run_id)
    return run_id


def get_run(physician, run_id: str) -> dict:
    fetched = physician.get(f"/api/v1/runs/{run_id}")
    assert fetched.status_code == 200
    return fetched.json()


def build_succeeded_run(physician, encounter_id, revision, key_prefix: str) -> str:
    """Start a real synthetic run and drive the worker to succeeded."""
    run_id = start_run(physician, encounter_id, revision, f"{key_prefix}-run")
    drain(key_prefix, max_steps=10)
    body = get_run(physician, run_id)
    assert body["run"]["status"] == "succeeded"
    assert body["proposal"]["status"] == "succeeded"
    assert body["stale"] is False
    return run_id


def plan_body(payload: dict) -> dict:
    if isinstance(payload, dict) and isinstance(payload.get("secondary_plan"), dict):
        return payload["secondary_plan"]
    return payload


def setup_succeeded_fixture(admin, physician, username, patient_pid, key_prefix):
    """Shared setup: physician + patient + clinical draft + succeeded run."""
    login(admin)
    create_physician(admin, username, f"s49-{username}-create")
    login(physician, username, "secret", "physician")
    _patient, encounter = create_patient(physician, patient_pid, f"{key_prefix}-p")
    encounter_id = encounter["id"]
    medications = [{"catalog_drug_id": MED_A}, {"catalog_drug_id": MED_B}]
    fingerprint = content_hash(
        {"resolved": sorted([MED_A, MED_B]), "unresolved": []}
    )
    saved = physician.patch(
        f"/api/v1/encounters/{encounter_id}",
        json={
            "draft_data": clinical_draft(
                medications, SYNTHETIC_DDI_VERSION, fingerprint
            )
        },
        headers=mutation_headers(physician, revision=encounter["revision"]),
    )
    assert saved.status_code == 200
    revision = current_revision(physician, encounter_id)
    run_id = build_succeeded_run(physician, encounter_id, revision, key_prefix)
    return encounter_id, run_id


def test_secondary_plan_save_preserves_initial_proposal():
    pair_key = canonical_pair_key(MED_A, MED_B)
    insert_ddi_release(
        SYNTHETIC_DDI_VERSION,
        [
            {
                "pair_key": pair_key,
                "source_severity": "monitor_closely",
                "management": "SYNTHETIC s49 management - test only",
                "direction": {"subject": MED_A, "object": MED_B},
                "source_path": "SYNTHETIC-s49.txt",
                "span": {"start_line": 1, "end_line": 2},
                "raw_text": "SYNTHETIC s49 evidence for pair coverage - test only",
            }
        ],
    )
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            encounter_id, run_id = setup_succeeded_fixture(
                admin, physician, "s49docA", "0799000491", "s49-s1"
            )
            before = get_run(physician, run_id)
            before_dump = json.dumps(before["proposal"], sort_keys=True)

            first = physician.patch(
                f"/api/v1/encounters/{encounter_id}/secondary-plan",
                json={"text": SECONDARY_V1},
                headers=mutation_headers(physician, key="s49-s1-plan-1", revision="0"),
            )
            assert first.status_code == 200
            saved_v1 = plan_body(first.json())
            assert saved_v1["text"] == SECONDARY_V1
            assert int(saved_v1["revision"]) == 1

            second = physician.patch(
                f"/api/v1/encounters/{encounter_id}/secondary-plan",
                json={"text": SECONDARY_V2},
                headers=mutation_headers(physician, key="s49-s1-plan-2", revision="1"),
            )
            assert second.status_code == 200
            saved_v2 = plan_body(second.json())
            assert saved_v2["text"] == SECONDARY_V2
            assert int(saved_v2["revision"]) == 2

            history = physician.get(
                f"/api/v1/encounters/{encounter_id}/secondary-plan"
            )
            assert history.status_code == 200
            seen = plan_body(history.json())
            assert seen["text"] == SECONDARY_V2
            assert int(seen["revision"]) == 2
            dumped_history = json.dumps(seen, sort_keys=True)
            assert SECONDARY_V1 in dumped_history
            assert SECONDARY_V2 in dumped_history

            after = get_run(physician, run_id)
            assert json.dumps(after["proposal"], sort_keys=True) == before_dump
            assert SECONDARY_V1 not in before_dump
            assert SECONDARY_V2 not in json.dumps(after["proposal"], sort_keys=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_sign_current_successful_run_with_revisions_and_acks():
    pair_key = canonical_pair_key(MED_A, MED_B)
    insert_ddi_release(
        SYNTHETIC_DDI_VERSION,
        [
            {
                "pair_key": pair_key,
                "source_severity": "monitor_closely",
                "management": "SYNTHETIC s49 management - test only",
                "direction": {"subject": MED_A, "object": MED_B},
                "source_path": "SYNTHETIC-s49.txt",
                "span": {"start_line": 1, "end_line": 2},
                "raw_text": "SYNTHETIC s49 evidence for pair coverage - test only",
            }
        ],
    )
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            encounter_id, run_id = setup_succeeded_fixture(
                admin, physician, "s49docB", "0799000492", "s49-s2"
            )
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}/secondary-plan",
                json={"text": SECONDARY_V1},
                headers=mutation_headers(physician, key="s49-s2-plan-1", revision="0"),
            )
            assert saved.status_code == 200
            secondary_revision = int(plan_body(saved.json())["revision"])
            assert secondary_revision == 1

            encounter_revision = current_revision(physician, encounter_id)
            run_body = get_run(physician, run_id)
            assert run_body["run"]["status"] == "succeeded"
            assert run_body["stale"] is False

            signed = physician.post(
                f"/api/v1/encounters/{encounter_id}/sign",
                json={
                    "encounter_revision": encounter_revision,
                    "run_id": run_id,
                    "secondary_plan_revision": secondary_revision,
                    "review_acknowledgments": [],
                    "baseline_acknowledgment": True,
                },
                headers=mutation_headers(
                    physician, key="s49-s2-sign-1", revision=encounter_revision
                ),
            )
            assert signed.status_code in (200, 201)
            payload = signed.json()
            encounter = (
                payload["encounter"] if isinstance(payload.get("encounter"), dict) else payload
            )
            assert encounter["state"] == "signed"
            assert encounter["id"] == encounter_id
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S49 slice 2 (RED): sign denial matrix (T1, real PostgreSQL + real pipeline).
#
# Scope: plan.md 4.3/9; tasks.md S49.2; FR-15/FR-22. The two slice-1 tests
# above are preserved unchanged. Every test below drives REAL pipeline runs
# (controlled localhost provider + real worker drain, single-question
# synthetic bundle identical to slice 1). No signable success flag is ever
# forged via direct SQL UPDATE of runs; SQL is setup-only (bundles/provider/
# DDI rows, signed-baseline fixture, newer-signed baseline fixture).
# ---------------------------------------------------------------------------


SYNTHETIC_FOLLOWUP_BUNDLE_HASH = "synthetic-bundle-hash-s49-followup"


def ddi_evidence() -> list[dict]:
    pair_key = canonical_pair_key(MED_A, MED_B)
    return [
        {
            "pair_key": pair_key,
            "source_severity": "monitor_closely",
            "management": "SYNTHETIC s49 management - test only",
            "direction": {"subject": MED_A, "object": MED_B},
            "source_path": "SYNTHETIC-s49.txt",
            "span": {"start_line": 1, "end_line": 2},
            "raw_text": "SYNTHETIC s49 evidence for pair coverage - test only",
        }
    ]


def save_plan(client, encounter_id, text_value, key, revision) -> int:
    saved = client.patch(
        f"/api/v1/encounters/{encounter_id}/secondary-plan",
        json={"text": text_value},
        headers=mutation_headers(client, key=key, revision=revision),
    )
    assert saved.status_code == 200
    return int(plan_body(saved.json())["revision"])


def post_sign(
    client,
    encounter_id,
    *,
    encounter_revision,
    run_id=None,
    plan_revision=0,
    ack=True,
    omit_ack=False,
    key,
    if_match=None,
    extra=None,
):
    body: dict = {
        "encounter_revision": encounter_revision,
        "secondary_plan_revision": plan_revision,
        "review_acknowledgments": [],
        "baseline_acknowledgment": ack,
    }
    if run_id is not None:
        body["run_id"] = run_id
    if omit_ack:
        body.pop("baseline_acknowledgment", None)
    if extra:
        body.update(extra)
    match = encounter_revision if if_match is None else if_match
    return client.post(
        f"/api/v1/encounters/{encounter_id}/sign",
        json=body,
        headers=mutation_headers(client, key=key, revision=match),
    )


def sign_baseline(encounter_id: str) -> None:
    """Fixture setup only: mark a registration draft signed via SQL."""
    with db.transaction() as conn:
        conn.execute(
            text("UPDATE encounters SET state = 'signed' WHERE id = :id"),
            {"id": str(encounter_id)},
        )


def enc_body(payload: dict) -> dict:
    if isinstance(payload, dict) and isinstance(payload.get("encounter"), dict):
        return payload["encounter"]
    return payload


def followup_draft(
    medications, ddi_version, ddi_fingerprint, recon_status, baseline_id
) -> dict:
    draft = clinical_draft(medications, ddi_version, ddi_fingerprint)
    draft["history_reconciliation"] = {
        "status": recon_status,
        "baseline_encounter_id": baseline_id,
    }
    return draft


def start_failing_provider(bodies: list[bytes]):
    """Controlled localhost provider that always fails (real HTTP 500)."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
            out = json.dumps(
                {"error": "synthetic provider failure - test only"}
            ).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

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


def drain_failures(worker_prefix: str, max_steps: int = 15) -> list[dict]:
    """Drain a failing run past the shared retry backoff (clock jumps).

    Same harness pattern as the S47 recovery suite: deterministic
    queue-clock jumps skip past the bounded backoff cap without real
    sleeps. Every assertion still reads public GET JSON + captured
    provider bodies.
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


def test_sign_rejects_absent_unknown_run_and_forged_manual_plan():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            encounter_id, run_id = setup_succeeded_fixture(
                admin, physician, "s49denA", "0799000493", "s49-d1"
            )
            plan_revision = save_plan(
                physician, encounter_id, SECONDARY_V1, "s49-d1-plan-1", "0"
            )
            assert plan_revision == 1
            revision = current_revision(physician, encounter_id)

            missing = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=None,
                plan_revision=plan_revision,
                key="s49-d1-sign-missing",
            )
            assert missing.status_code == 422

            forged = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=None,
                plan_revision=plan_revision,
                key="s49-d1-sign-forged",
                extra={"manual_plan": "SYNTHETIC free-text manual plan - test only"},
            )
            assert forged.status_code == 422

            smuggled = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-d1-sign-smuggled",
                extra={"manual_plan": "SYNTHETIC free-text manual plan - test only"},
            )
            assert smuggled.status_code == 422

            unknown = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=str(uuid.uuid4()),
                plan_revision=plan_revision,
                key="s49-d1-sign-unknown",
            )
            assert unknown.status_code == 404

            ok = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-d1-sign-ok",
            )
            assert ok.status_code in (200, 201)
            assert enc_body(ok.json())["state"] == "signed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_sign_rejects_failed_and_partial_run():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_failing_provider(bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            login(admin)
            create_physician(admin, "s49denB", "s49-s49denB-create")
            login(physician, "s49denB", "secret", "physician")
            _patient, encounter = create_patient(
                physician, "0799000494", "s49-d2-p"
            )
            encounter_id = encounter["id"]
            medications = [{"catalog_drug_id": MED_A}, {"catalog_drug_id": MED_B}]
            fingerprint = content_hash(
                {"resolved": sorted([MED_A, MED_B]), "unresolved": []}
            )
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={
                    "draft_data": clinical_draft(
                        medications, SYNTHETIC_DDI_VERSION, fingerprint
                    )
                },
                headers=mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = current_revision(physician, encounter_id)
            run_id = start_run(physician, encounter_id, revision, "s49-d2-run")
            plan_revision = save_plan(
                physician, encounter_id, SECONDARY_V1, "s49-d2-plan-1", "0"
            )

            fresh = get_run(physician, run_id)
            assert fresh["run"]["status"] != "succeeded"
            partial = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-d2-sign-partial",
            )
            assert partial.status_code == 409

            drain_failures("s49-d2", max_steps=15)
            failed = get_run(physician, run_id)
            assert failed["run"]["status"] == "failed"
            assert failed["proposal"] is None
            assert len(bodies) >= 1

            denied = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-d2-sign-failed",
            )
            assert denied.status_code == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_sign_rejects_stale_run_but_note_only_stays_signable():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            # Stale fixture: analytical medication change after a real success.
            stale_id, stale_run = setup_succeeded_fixture(
                admin, physician, "s49denC", "0799000495", "s49-d3s"
            )
            stale_plan = save_plan(
                physician, stale_id, SECONDARY_V1, "s49-d3s-plan-1", "0"
            )
            stale_rev = current_revision(physician, stale_id)
            assert get_run(physician, stale_run)["stale"] is False
            fingerprint = content_hash(
                {"resolved": sorted([MED_A, MED_B]), "unresolved": []}
            )
            changed = physician.patch(
                f"/api/v1/encounters/{stale_id}",
                json={
                    "draft_data": clinical_draft(
                        [{"catalog_drug_id": MED_A}],
                        SYNTHETIC_DDI_VERSION,
                        fingerprint,
                    )
                },
                headers=mutation_headers(physician, revision=stale_rev),
            )
            assert changed.status_code == 200
            fresh_rev = current_revision(physician, stale_id)
            assert fresh_rev == stale_rev + 1
            assert get_run(physician, stale_run)["stale"] is True
            denied = post_sign(
                physician,
                stale_id,
                encounter_revision=fresh_rev,
                run_id=stale_run,
                plan_revision=stale_plan,
                key="s49-d3s-sign-stale",
            )
            assert denied.status_code == 409

            # Note-only fixture: a page note never changes the fingerprint.
            note_id, note_run = setup_succeeded_fixture(
                admin, physician, "s49denCn", "0799000496", "s49-d3n"
            )
            note_plan = save_plan(
                physician, note_id, SECONDARY_V1, "s49-d3n-plan-1", "0"
            )
            note_rev = current_revision(physician, note_id)
            noted = physician.post(
                f"/api/v1/encounters/{note_id}/notes",
                json={"page": "history", "text": "SYNTHETIC-S49-NOTE-test-only"},
                headers=mutation_headers(physician, key="s49-d3n-note-1"),
            )
            assert noted.status_code == 201
            assert current_revision(physician, note_id) == note_rev
            assert get_run(physician, note_run)["stale"] is False
            ok = post_sign(
                physician,
                note_id,
                encounter_revision=note_rev,
                run_id=note_run,
                plan_revision=note_plan,
                key="s49-d3n-sign-ok",
            )
            assert ok.status_code in (200, 201)
            assert enc_body(ok.json())["state"] == "signed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_sign_rejects_wrong_author_admin_and_anon():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with (
            TestClient(app) as admin,
            TestClient(app) as author,
            TestClient(app) as other,
        ):
            login(admin)
            create_physician(admin, "s49denE", "s49-s49denE-create")
            create_physician(admin, "s49denF", "s49-s49denF-create")
            login(author, "s49denE", "secret", "physician")
            login(other, "s49denF", "secret", "physician")
            _patient, encounter = create_patient(author, "0799000497", "s49-d5-p")
            encounter_id = encounter["id"]
            medications = [{"catalog_drug_id": MED_A}, {"catalog_drug_id": MED_B}]
            fingerprint = content_hash(
                {"resolved": sorted([MED_A, MED_B]), "unresolved": []}
            )
            saved = author.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={
                    "draft_data": clinical_draft(
                        medications, SYNTHETIC_DDI_VERSION, fingerprint
                    )
                },
                headers=mutation_headers(author, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = current_revision(author, encounter_id)
            run_id = build_succeeded_run(author, encounter_id, revision, "s49-d5")
            plan_revision = save_plan(
                author, encounter_id, SECONDARY_V1, "s49-d5-plan-1", "0"
            )

            other_denied = post_sign(
                other,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-d5-sign-other",
            )
            assert other_denied.status_code == 403

            admin_denied = post_sign(
                admin,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-d5-sign-admin",
            )
            assert admin_denied.status_code == 403

            ok = post_sign(
                author,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-d5-sign-ok",
            )
            assert ok.status_code in (200, 201)
            assert enc_body(ok.json())["state"] == "signed"

        with TestClient(app) as anon:
            anon_denied = anon.post(
                f"/api/v1/encounters/{encounter_id}/sign",
                json={
                    "encounter_revision": revision,
                    "run_id": run_id,
                    "secondary_plan_revision": plan_revision,
                    "review_acknowledgments": [],
                    "baseline_acknowledgment": True,
                },
            )
            assert anon_denied.status_code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_sign_rejects_outdated_encounter_and_plan_revisions():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            encounter_id, run_id = setup_succeeded_fixture(
                admin, physician, "s49denG", "0799000498", "s49-d6"
            )
            plan_v1 = save_plan(
                physician, encounter_id, SECONDARY_V1, "s49-d6-plan-1", "0"
            )
            assert plan_v1 == 1
            revision = current_revision(physician, encounter_id)

            stale_encounter = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision - 1,
                run_id=run_id,
                plan_revision=plan_v1,
                key="s49-d6-sign-old-enc",
                if_match=revision - 1,
            )
            assert stale_encounter.status_code == 412

            stale_plan = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=0,
                key="s49-d6-sign-old-plan",
            )
            assert stale_plan.status_code == 409

            plan_v2 = save_plan(
                physician, encounter_id, SECONDARY_V2, "s49-d6-plan-2", "1"
            )
            assert plan_v2 == 2
            outdated_plan = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=1,
                key="s49-d6-sign-outdated-plan",
            )
            assert outdated_plan.status_code == 409

            ok = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_v2,
                key="s49-d6-sign-ok",
            )
            assert ok.status_code in (200, 201)
            assert enc_body(ok.json())["state"] == "signed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_sign_rejects_unreconciled_followup_baseline_and_accepts_reconciled():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    insert_bundle_for("followup", SYNTHETIC_FOLLOWUP_BUNDLE_HASH)
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            login(admin)
            create_physician(admin, "s49denH", "s49-s49denH-create")
            me = login(physician, "s49denH", "secret", "physician")
            medications = [{"catalog_drug_id": MED_A}, {"catalog_drug_id": MED_B}]
            fingerprint = content_hash(
                {"resolved": sorted([MED_A, MED_B]), "unresolved": []}
            )

            # Reconciled fixture: confirmed reconciliation + ack succeeds.
            patient_ok, baseline_ok = create_patient(
                physician, "0799000499", "s49-d7-ok-p"
            )
            seeded_ok = physician.patch(
                f"/api/v1/encounters/{baseline_ok['id']}",
                json={
                    "draft_data": clinical_draft(
                        medications, SYNTHETIC_DDI_VERSION, fingerprint
                    )
                },
                headers=mutation_headers(
                    physician, revision=baseline_ok["revision"]
                ),
            )
            assert seeded_ok.status_code == 200
            sign_baseline(baseline_ok["id"])
            created_ok = physician.post(
                f"/api/v1/patients/{patient_ok['id']}/encounters",
                json={"baseline_encounter_id": baseline_ok["id"]},
                headers=mutation_headers(physician, "s49-d7-ok-followup"),
            )
            assert created_ok.status_code == 201
            followup_ok = enc_body(created_ok.json())
            assert followup_ok["kind"] == "follow_up"
            assert followup_ok["draft_data"]["history_reconciliation"] == {
                "status": "pending",
                "baseline_encounter_id": baseline_ok["id"],
            }
            assert followup_ok["baseline_changed"] is False
            confirmed_ok = physician.patch(
                f"/api/v1/encounters/{followup_ok['id']}",
                json={
                    "draft_data": followup_draft(
                        medications,
                        SYNTHETIC_DDI_VERSION,
                        fingerprint,
                        "confirmed",
                        baseline_ok["id"],
                    )
                },
                headers=mutation_headers(physician, revision=1),
            )
            assert confirmed_ok.status_code == 200
            revision_ok = current_revision(physician, followup_ok["id"])
            run_ok = build_succeeded_run(
                physician, followup_ok["id"], revision_ok, "s49-d7-ok"
            )
            plan_ok = save_plan(
                physician, followup_ok["id"], SECONDARY_V1, "s49-d7-ok-plan-1", "0"
            )
            ok = post_sign(
                physician,
                followup_ok["id"],
                encounter_revision=revision_ok,
                run_id=run_ok,
                plan_revision=plan_ok,
                ack=True,
                key="s49-d7-ok-sign",
            )
            assert ok.status_code in (200, 201)
            assert enc_body(ok.json())["state"] == "signed"

            # Pending fixture: missing/false ack rejected, pending + ack
            # rejected even though the run itself succeeded.
            patient_pending, baseline_pending = create_patient(
                physician, "0799000500", "s49-d7-pend-p"
            )
            seeded_pending = physician.patch(
                f"/api/v1/encounters/{baseline_pending['id']}",
                json={
                    "draft_data": clinical_draft(
                        medications, SYNTHETIC_DDI_VERSION, fingerprint
                    )
                },
                headers=mutation_headers(
                    physician, revision=baseline_pending["revision"]
                ),
            )
            assert seeded_pending.status_code == 200
            sign_baseline(baseline_pending["id"])
            created_pending = physician.post(
                f"/api/v1/patients/{patient_pending['id']}/encounters",
                json={"baseline_encounter_id": baseline_pending["id"]},
                headers=mutation_headers(physician, "s49-d7-pend-followup"),
            )
            assert created_pending.status_code == 201
            followup_pending = enc_body(created_pending.json())
            assert followup_pending["draft_data"]["history_reconciliation"] == {
                "status": "pending",
                "baseline_encounter_id": baseline_pending["id"],
            }
            # Seed analysis-visible facts (incl. the DDI report reference the
            # proposal assembly pins) while leaving reconciliation pending.
            seeded_pending_draft = physician.patch(
                f"/api/v1/encounters/{followup_pending['id']}",
                json={
                    "draft_data": followup_draft(
                        medications,
                        SYNTHETIC_DDI_VERSION,
                        fingerprint,
                        "pending",
                        baseline_pending["id"],
                    )
                },
                headers=mutation_headers(physician, revision=1),
            )
            assert seeded_pending_draft.status_code == 200
            revision_pending = current_revision(physician, followup_pending["id"])
            run_pending = build_succeeded_run(
                physician, followup_pending["id"], revision_pending, "s49-d7-pend"
            )
            plan_pending = save_plan(
                physician,
                followup_pending["id"],
                SECONDARY_V1,
                "s49-d7-pend-plan-1",
                "0",
            )
            no_ack = post_sign(
                physician,
                followup_pending["id"],
                encounter_revision=revision_pending,
                run_id=run_pending,
                plan_revision=plan_pending,
                ack=False,
                key="s49-d7-pend-sign-noack",
            )
            assert no_ack.status_code == 409
            missing_ack = post_sign(
                physician,
                followup_pending["id"],
                encounter_revision=revision_pending,
                run_id=run_pending,
                plan_revision=plan_pending,
                omit_ack=True,
                key="s49-d7-pend-sign-missingack",
            )
            assert missing_ack.status_code == 409
            pending_denied = post_sign(
                physician,
                followup_pending["id"],
                encounter_revision=revision_pending,
                run_id=run_pending,
                plan_revision=plan_pending,
                ack=True,
                key="s49-d7-pend-sign",
            )
            assert pending_denied.status_code == 409

            # Changed-baseline fixture: a newer signed record exists, so
            # even a confirmed reconciliation + ack must be rejected until
            # the draft re-reconciles against the new baseline.
            patient_chg, baseline_chg = create_patient(
                physician, "0799000501", "s49-d7-chg-p"
            )
            seeded_chg = physician.patch(
                f"/api/v1/encounters/{baseline_chg['id']}",
                json={
                    "draft_data": clinical_draft(
                        medications, SYNTHETIC_DDI_VERSION, fingerprint
                    )
                },
                headers=mutation_headers(
                    physician, revision=baseline_chg["revision"]
                ),
            )
            assert seeded_chg.status_code == 200
            sign_baseline(baseline_chg["id"])
            created_chg = physician.post(
                f"/api/v1/patients/{patient_chg['id']}/encounters",
                json={"baseline_encounter_id": baseline_chg["id"]},
                headers=mutation_headers(physician, "s49-d7-chg-followup"),
            )
            assert created_chg.status_code == 201
            followup_chg = enc_body(created_chg.json())
            confirmed_chg = physician.patch(
                f"/api/v1/encounters/{followup_chg['id']}",
                json={
                    "draft_data": followup_draft(
                        medications,
                        SYNTHETIC_DDI_VERSION,
                        fingerprint,
                        "confirmed",
                        baseline_chg["id"],
                    )
                },
                headers=mutation_headers(physician, revision=1),
            )
            assert confirmed_chg.status_code == 200
            revision_chg = current_revision(physician, followup_chg["id"])
            run_chg = build_succeeded_run(
                physician, followup_chg["id"], revision_chg, "s49-d7-chg"
            )
            plan_chg = save_plan(
                physician,
                followup_chg["id"],
                SECONDARY_V1,
                "s49-d7-chg-plan-1",
                "0",
            )
            with db.transaction() as conn:
                conn.execute(
                    text(
                        "INSERT INTO encounters "
                        "(patient_id, kind, author_id, state, draft_data) "
                        "VALUES (:pid, 'registration', :author, 'signed', "
                        "CAST(:data AS jsonb))"
                    ),
                    {
                        "pid": str(patient_chg["id"]),
                        "author": str(me["user"]["id"]),
                        "data": "{}",
                    },
                )
            refetched = physician.get(f"/api/v1/encounters/{followup_chg['id']}")
            assert refetched.status_code == 200
            assert enc_body(refetched.json())["baseline_changed"] is True
            assert get_run(physician, run_chg)["stale"] is False
            changed_denied = post_sign(
                physician,
                followup_chg["id"],
                encounter_revision=revision_chg,
                run_id=run_chg,
                plan_revision=plan_chg,
                ack=True,
                key="s49-d7-chg-sign",
            )
            assert changed_denied.status_code == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S49 slice 3 (RED, T1): full atomic freeze + idempotent replay + no partial.
#
# Scope: plan.md 4.1-4.3, 9; tasks.md S49.3; FR-15/FR-22. Slices 1-2 tests
# above are preserved unchanged. Every test below drives REAL pipeline runs
# (controlled localhost provider + real worker drain, single-question
# synthetic bundle identical to slices 1-2). No signable success flag is
# ever forged via direct SQL UPDATE of runs; SQL is setup-only
# (bundles/provider/DDI rows). Synthetic values only.
#
# Minimal proposed contract under test (not yet implemented in signing.py):
# - POST /api/v1/encounters/{id}/sign success atomically freezes the full
#   displayed record and returns a full signed_snapshot payload.
# - GET /api/v1/encounters/{id}/signed-snapshot returns 200 with the same
#   frozen snapshot + snapshot_hash after success, 404 before any success.
# - Minimal frozen shape: patient demographics, draft_data
#   (diagnosis/history/effects/medications/ddi_report + panss/cssrs when
#   present), notes [{page,author_id,author_display,created_at,text}],
#   medications + ddi_report, content/bundle versions
#   {bundle_hash,pinned,provider_revision}, initial_proposal byte-identical
#   to GET /runs/{id} proposal, secondary_plan {revision,text},
#   signer_id/signed_at, snapshot_hash. Audit encounter.sign exists with the
#   same encounter reference.
# Current signing.py freezes only a minimal snapshot
# (encounter/patient_id/kind/revision/draft_data/run_id/secondary revision+
# text/signer/time) with no readable GET, so the GET assertions below fail
# with 404 and the full-key assertions fail on the minimal payload.
# ---------------------------------------------------------------------------


S49_S3_NOTE = "SYNTHETIC-S49-SLICE3-NOTE-test-only"


def fetch_snapshot(physician, encounter_id):
    return physician.get(f"/api/v1/encounters/{encounter_id}/signed-snapshot")


def test_sign_freezes_full_record_and_exposes_signed_snapshot():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            encounter_id, run_id = setup_succeeded_fixture(
                admin, physician, "s49sigA", "0799000510", "s49-s3a"
            )
            before = get_run(physician, run_id)
            before_dump = json.dumps(before["proposal"], sort_keys=True)
            pinned_before = before.get("pinned", {})

            plan_revision = save_plan(
                physician, encounter_id, SECONDARY_V1, "s49-s3a-plan-1", "0"
            )
            assert plan_revision == 1

            noted = physician.post(
                f"/api/v1/encounters/{encounter_id}/notes",
                json={"page": "history", "text": S49_S3_NOTE},
                headers=mutation_headers(physician, key="s49-s3a-note-1"),
            )
            assert noted.status_code == 201
            note = noted.json()["note"]

            enc_before = physician.get(f"/api/v1/encounters/{encounter_id}")
            assert enc_before.status_code == 200
            draft_before = enc_before.json()["encounter"]["draft_data"]
            assert "medications" in draft_before
            assert "ddi_report" in draft_before

            notes_before = physician.get(f"/api/v1/encounters/{encounter_id}/notes")
            assert notes_before.status_code == 200
            assert any(
                item["text"] == S49_S3_NOTE
                for item in notes_before.json()["items"]
            )

            listed = physician.get("/api/v1/patients?q=0799000510")
            assert listed.status_code == 200
            patient_before = listed.json()["items"][0]
            assert patient_before["patient_id"] == "0799000510"

            # No snapshot before success under the proposed contract.
            assert fetch_snapshot(physician, encounter_id).status_code == 404

            revision = current_revision(physician, encounter_id)
            signed = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-s3a-sign-1",
            )
            assert signed.status_code in (200, 201)
            payload = signed.json()
            assert enc_body(payload)["state"] == "signed"
            assert payload["signed_snapshot"]["snapshot_hash"]

            # Proposed readable freeze: must be 200 with all keys + hash.
            snap_resp = fetch_snapshot(physician, encounter_id)
            assert snap_resp.status_code == 200
            snap_body = snap_resp.json()
            frozen = snap_body["signed_snapshot"]
            assert frozen["snapshot_hash"] == payload["signed_snapshot"]["snapshot_hash"]
            assert frozen["encounter_id"] == encounter_id
            assert frozen["patient"]["patient_id"] == "0799000510"
            assert frozen["patient"]["first_name"] == patient_before["first_name"]
            for key in (
                "diagnosis",
                "history",
                "effects",
                "medications",
                "ddi_report",
            ):
                assert key in frozen["draft_data"]
                assert frozen["draft_data"][key] == draft_before[key]
            assert any(
                entry["text"] == S49_S3_NOTE
                and entry["page"] == "history"
                and entry["author_id"] == note["author_id"]
                for entry in frozen["notes"]
            )
            assert frozen["medications"] == draft_before["medications"]
            assert frozen["ddi_report"] == draft_before["ddi_report"]
            assert frozen["content_versions"]["pinned"] == pinned_before
            assert json.dumps(
                frozen["initial_proposal"], sort_keys=True
            ) == before_dump
            assert frozen["secondary_plan"]["text"] == SECONDARY_V1
            assert int(frozen["secondary_plan"]["revision"]) == plan_revision
            assert frozen["signer_id"]
            assert frozen["signed_at"]

            # Live reads stay consistent with the freeze.
            after = get_run(physician, run_id)
            assert json.dumps(after["proposal"], sort_keys=True) == before_dump
            plan_after = physician.get(
                f"/api/v1/encounters/{encounter_id}/secondary-plan"
            )
            assert plan_after.status_code == 200
            assert plan_body(plan_after.json())["text"] == SECONDARY_V1

            # Same-request audit exists (public seam exposes reference only).
            events = admin.get(
                "/api/v1/audit-events?operation=encounter.sign&limit=100"
            )
            assert events.status_code == 200
            assert any(
                item["operation"] == "encounter.sign"
                and item["result_reference"] == encounter_id
                for item in events.json()["items"]
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_sign_idempotent_replay_returns_same_hash_and_conflicts_on_changed_body():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            encounter_id, run_id = setup_succeeded_fixture(
                admin, physician, "s49sigB", "0799000511", "s49-s3b"
            )
            plan_revision = save_plan(
                physician, encounter_id, SECONDARY_V1, "s49-s3b-plan-1", "0"
            )
            revision = current_revision(physician, encounter_id)

            first = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-s3b-sign-1",
            )
            assert first.status_code in (200, 201)
            first_hash = first.json()["signed_snapshot"]["snapshot_hash"]
            signed_revision = int(enc_body(first.json())["revision"])

            # Identical key + identical body replays the same signature.
            replay = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-s3b-sign-1",
            )
            assert replay.status_code == first.status_code
            assert (
                replay.json()["signed_snapshot"]["snapshot_hash"] == first_hash
            )
            assert int(enc_body(replay.json())["revision"]) == signed_revision
            assert current_revision(physician, encounter_id) == signed_revision

            # Proposed readable snapshot is stable across the replay.
            snap_resp = fetch_snapshot(physician, encounter_id)
            assert snap_resp.status_code == 200
            assert (
                snap_resp.json()["signed_snapshot"]["snapshot_hash"] == first_hash
            )

            # Same key + changed body must conflict, never re-sign.
            conflicted = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-s3b-sign-1",
                extra={
                    "review_acknowledgments": [
                        "SYNTHETIC-changed-ack-test-only"
                    ]
                },
            )
            assert conflicted.status_code == 409
            assert current_revision(physician, encounter_id) == signed_revision
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_failed_sign_leaves_no_snapshot_and_success_creates_single_snapshot():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            login(admin)
            create_physician(admin, "s49sigC", "s49-s49sigC-create")
            login(physician, "s49sigC", "secret", "physician")

            # Stale fixture: analytical medication change after success.
            _patient_s, encounter_s = create_patient(
                physician, "0799000512", "s49-s3c-p-stale"
            )
            stale_id = encounter_s["id"]
            medications = [{"catalog_drug_id": MED_A}, {"catalog_drug_id": MED_B}]
            fingerprint = content_hash(
                {"resolved": sorted([MED_A, MED_B]), "unresolved": []}
            )
            seeded = physician.patch(
                f"/api/v1/encounters/{stale_id}",
                json={
                    "draft_data": clinical_draft(
                        medications, SYNTHETIC_DDI_VERSION, fingerprint
                    )
                },
                headers=mutation_headers(physician, revision=encounter_s["revision"]),
            )
            assert seeded.status_code == 200
            stale_rev0 = current_revision(physician, stale_id)
            stale_run = build_succeeded_run(physician, stale_id, stale_rev0, "s49-s3c")
            stale_plan = save_plan(
                physician, stale_id, SECONDARY_V1, "s49-s3c-plan-1", "0"
            )
            changed = physician.patch(
                f"/api/v1/encounters/{stale_id}",
                json={
                    "draft_data": clinical_draft(
                        [{"catalog_drug_id": MED_A}],
                        SYNTHETIC_DDI_VERSION,
                        fingerprint,
                    )
                },
                headers=mutation_headers(physician, revision=stale_rev0),
            )
            assert changed.status_code == 200
            fresh_rev = current_revision(physician, stale_id)
            assert get_run(physician, stale_run)["stale"] is True

            denied = post_sign(
                physician,
                stale_id,
                encounter_revision=fresh_rev,
                run_id=stale_run,
                plan_revision=stale_plan,
                key="s49-s3c-sign-stale",
            )
            assert denied.status_code == 409
            # Observable atomicity: draft untouched, no snapshot, no success
            # audit for the denied encounter.
            still = physician.get(f"/api/v1/encounters/{stale_id}")
            assert still.status_code == 200
            assert still.json()["encounter"]["state"] == "draft"
            assert int(still.json()["encounter"]["revision"]) == fresh_rev
            assert fetch_snapshot(physician, stale_id).status_code == 404
            events = admin.get(
                "/api/v1/audit-events?operation=encounter.sign&limit=100"
            )
            assert events.status_code == 200
            assert not any(
                item["result_reference"] == stale_id
                for item in events.json()["items"]
            )

            # Clean control under the same author: success freezes exactly
            # one readable snapshot; replay does not bump revision.
            _patient_ok, encounter_ok = create_patient(
                physician, "0799000513", "s49-s3c-p-ok"
            )
            ok_id = encounter_ok["id"]
            seeded_ok = physician.patch(
                f"/api/v1/encounters/{ok_id}",
                json={
                    "draft_data": clinical_draft(
                        medications, SYNTHETIC_DDI_VERSION, fingerprint
                    )
                },
                headers=mutation_headers(physician, revision=encounter_ok["revision"]),
            )
            assert seeded_ok.status_code == 200
            ok_rev = current_revision(physician, ok_id)
            ok_run = build_succeeded_run(physician, ok_id, ok_rev, "s49-s3c-ok")
            ok_plan = save_plan(
                physician, ok_id, SECONDARY_V1, "s49-s3c-ok-plan-1", "0"
            )
            ok = post_sign(
                physician,
                ok_id,
                encounter_revision=ok_rev,
                run_id=ok_run,
                plan_revision=ok_plan,
                key="s49-s3c-sign-ok",
            )
            assert ok.status_code in (200, 201)
            ok_hash = ok.json()["signed_snapshot"]["snapshot_hash"]
            ok_signed_rev = int(enc_body(ok.json())["revision"])
            snap_ok = fetch_snapshot(physician, ok_id)
            assert snap_ok.status_code == 200
            assert snap_ok.json()["signed_snapshot"]["snapshot_hash"] == ok_hash
            replay_ok = post_sign(
                physician,
                ok_id,
                encounter_revision=ok_rev,
                run_id=ok_run,
                plan_revision=ok_plan,
                key="s49-s3c-sign-ok",
            )
            assert (
                replay_ok.json()["signed_snapshot"]["snapshot_hash"] == ok_hash
            )
            assert current_revision(physician, ok_id) == ok_signed_rev
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S49 slice 4 (RED, T1): post-sign immutability + demographics freeze + addenda.
#
# Scope: plan.md 9; tasks.md S49.4; FR-15/FR-22. Slices 1-3 tests above are
# preserved unchanged. Every test below drives REAL pipeline runs
# (controlled localhost provider + real worker drain, single-question
# synthetic bundle identical to slices 1-3). No signable success flag is
# ever forged via direct SQL UPDATE of runs; SQL is setup-only
# (bundles/provider/DDI rows). Synthetic values only.
#
# Terminal-state convention under test: after successful sign, any
# clinical/plan/note mutation through any route is 409 CONFLICT (same as
# the existing discard convention for non-draft state). 409 is chosen over
# 403 because the caller is authorized but the resource is in a terminal
# state. Each denial must leave GET signed-snapshot byte-identical.
# Current patient demographics (phone) may still change (200) without
# rewriting the frozen historical snapshot. Addenda are original-signer
# only, attributed, append-only; the frozen snapshot never changes.
# Addenda routes do not exist yet, so slice-4 addendum assertions fail
# with 404 = RED. Notes-after-sign currently succeeds (201), so the
# immutability test also fails RED on the notes denial.
# ---------------------------------------------------------------------------


S49_S4_NOTE = "SYNTHETIC-S49-SLICE4-NOTE-test-only"
S49_S4_PHONE = "SYNTHETIC-S49-PHONE-001-test-only"
S49_S4_REASON = "SYNTHETIC-S49-ADDENDUM-REASON-test-only"
S49_S4_TEXT = "SYNTHETIC-S49-ADDENDUM-TEXT-test-only"
S49_S4_TEXT_TWO = "SYNTHETIC-S49-ADDENDUM-TEXT-TWO-test-only"


def snapshot_dump(physician, encounter_id) -> tuple[str, dict]:
    resp = fetch_snapshot(physician, encounter_id)
    assert resp.status_code == 200
    frozen = resp.json()["signed_snapshot"]
    return json.dumps(frozen, sort_keys=True), frozen


def test_signed_encounter_rejects_later_clinical_plan_note_mutations():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            encounter_id, run_id = setup_succeeded_fixture(
                admin, physician, "s49sigD", "0799000514", "s49-s4a"
            )
            plan_revision = save_plan(
                physician, encounter_id, SECONDARY_V1, "s49-s4a-plan-1", "0"
            )
            assert plan_revision == 1
            revision = current_revision(physician, encounter_id)
            signed = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-s4a-sign-1",
            )
            assert signed.status_code in (200, 201)
            assert enc_body(signed.json())["state"] == "signed"
            signed_hash = signed.json()["signed_snapshot"]["snapshot_hash"]
            signed_revision = int(enc_body(signed.json())["revision"])
            snap_resp = fetch_snapshot(physician, encounter_id)
            assert snap_resp.status_code == 200
            assert (
                snap_resp.json()["signed_snapshot"]["snapshot_hash"] == signed_hash
            )
            before_dump, _ = snapshot_dump(physician, encounter_id)

            fingerprint = content_hash(
                {"resolved": sorted([MED_A, MED_B]), "unresolved": []}
            )
            draft_denied = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={
                    "draft_data": clinical_draft(
                        [{"catalog_drug_id": MED_A}],
                        SYNTHETIC_DDI_VERSION,
                        fingerprint,
                    )
                },
                headers=mutation_headers(physician, revision=signed_revision),
            )
            assert draft_denied.status_code == 409
            assert snapshot_dump(physician, encounter_id)[0] == before_dump

            discard_denied = physician.post(
                f"/api/v1/encounters/{encounter_id}/discard",
                json={"confirm": True},
                headers=mutation_headers(physician, revision=signed_revision),
            )
            assert discard_denied.status_code == 409
            assert snapshot_dump(physician, encounter_id)[0] == before_dump

            # Terminal-state choice: 409 CONFLICT (not 403) per existing
            # discard convention for non-draft state.
            note_denied = physician.post(
                f"/api/v1/encounters/{encounter_id}/notes",
                json={"page": "history", "text": S49_S4_NOTE},
                headers=mutation_headers(physician, key="s49-s4a-note-postsign"),
            )
            assert note_denied.status_code == 409
            assert snapshot_dump(physician, encounter_id)[0] == before_dump

            plan_denied = physician.patch(
                f"/api/v1/encounters/{encounter_id}/secondary-plan",
                json={"text": "SYNTHETIC-S49-SLICE4-PLAN-postsign-test-only"},
                headers=mutation_headers(
                    physician,
                    key="s49-s4a-plan-postsign",
                    revision=str(plan_revision),
                ),
            )
            assert plan_denied.status_code == 409
            assert snapshot_dump(physician, encounter_id)[0] == before_dump

            still = physician.get(f"/api/v1/encounters/{encounter_id}")
            assert still.status_code == 200
            assert still.json()["encounter"]["state"] == "signed"
            assert int(still.json()["encounter"]["revision"]) == signed_revision
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_current_demographics_change_preserves_historical_snapshot():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            encounter_id, run_id = setup_succeeded_fixture(
                admin, physician, "s49sigE", "0799000515", "s49-s4b"
            )
            plan_revision = save_plan(
                physician, encounter_id, SECONDARY_V1, "s49-s4b-plan-1", "0"
            )
            revision = current_revision(physician, encounter_id)
            signed = post_sign(
                physician,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-s4b-sign-1",
            )
            assert signed.status_code in (200, 201)
            signed_hash = signed.json()["signed_snapshot"]["snapshot_hash"]
            before_dump, before_frozen = snapshot_dump(physician, encounter_id)
            assert before_frozen["snapshot_hash"] == signed_hash
            original_phone = before_frozen["patient"]["phone"]
            original_first = before_frozen["patient"]["first_name"]

            listed = physician.get("/api/v1/patients?q=0799000515")
            assert listed.status_code == 200
            current = [
                item
                for item in listed.json()["items"]
                if item["patient_id"] == "0799000515"
            ][0]
            patient_uuid = current["id"]
            patient_revision = int(current["revision"])

            patched = physician.patch(
                f"/api/v1/patients/{patient_uuid}",
                json={"phone": S49_S4_PHONE},
                headers=mutation_headers(physician, revision=patient_revision),
            )
            assert patched.status_code == 200
            assert patched.json()["patient"]["phone"] == S49_S4_PHONE

            relisted = physician.get("/api/v1/patients?q=0799000515")
            assert relisted.status_code == 200
            now = [
                item
                for item in relisted.json()["items"]
                if item["patient_id"] == "0799000515"
            ][0]
            assert now["phone"] == S49_S4_PHONE

            after_dump, after_frozen = snapshot_dump(physician, encounter_id)
            assert after_dump == before_dump
            assert after_frozen["snapshot_hash"] == signed_hash
            assert after_frozen["patient"]["phone"] == original_phone
            assert after_frozen["patient"]["first_name"] == original_first
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _addendum_entry(payload: dict) -> dict:
    if isinstance(payload.get("addendum"), dict):
        return payload["addendum"]
    return payload


def _addendum_items(payload: dict) -> list[dict]:
    if isinstance(payload.get("items"), list):
        return payload["items"]
    if isinstance(payload.get("addenda"), list):
        return payload["addenda"]
    return []


def test_original_signer_addendum_is_attributed_and_immutable():
    insert_ddi_release(SYNTHETIC_DDI_VERSION, ddi_evidence())
    insert_bundle()
    bodies: list[bytes] = []
    server, thread = start_provider(synthetic_cpt_payload(SYNTHETIC_QUESTION), bodies)
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with (
            TestClient(app) as admin,
            TestClient(app) as author,
            TestClient(app) as other,
        ):
            login(admin)
            create_physician(admin, "s49sigF", "s49-s49sigF-create")
            create_physician(admin, "s49sigG", "s49-s49sigG-create")
            login(author, "s49sigF", "secret", "physician")
            login(other, "s49sigG", "secret", "physician")
            _patient, encounter = create_patient(author, "0799000516", "s49-s4c-p")
            encounter_id = encounter["id"]
            medications = [{"catalog_drug_id": MED_A}, {"catalog_drug_id": MED_B}]
            fingerprint = content_hash(
                {"resolved": sorted([MED_A, MED_B]), "unresolved": []}
            )
            seeded = author.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={
                    "draft_data": clinical_draft(
                        medications, SYNTHETIC_DDI_VERSION, fingerprint
                    )
                },
                headers=mutation_headers(author, revision=encounter["revision"]),
            )
            assert seeded.status_code == 200
            revision = current_revision(author, encounter_id)
            run_id = build_succeeded_run(author, encounter_id, revision, "s49-s4c")
            plan_revision = save_plan(
                author, encounter_id, SECONDARY_V1, "s49-s4c-plan-1", "0"
            )
            signed = post_sign(
                author,
                encounter_id,
                encounter_revision=revision,
                run_id=run_id,
                plan_revision=plan_revision,
                key="s49-s4c-sign-1",
            )
            assert signed.status_code in (200, 201)
            signer_id = signed.json()["signed_snapshot"]["signer_id"]
            signed_hash = signed.json()["signed_snapshot"]["snapshot_hash"]
            before_dump, _ = snapshot_dump(author, encounter_id)

            body_one = {"reason": S49_S4_REASON, "correction_text": S49_S4_TEXT}
            created = author.post(
                f"/api/v1/encounters/{encounter_id}/addenda",
                json=body_one,
                headers=mutation_headers(author, key="s49-s4c-add-1"),
            )
            assert created.status_code == 201
            entry = _addendum_entry(created.json())
            assert entry["reason"] == S49_S4_REASON
            assert entry["correction_text"] == S49_S4_TEXT
            assert entry["author_id"] == signer_id
            assert entry["created_at"]
            assert entry["id"]

            listed_resp = author.get(f"/api/v1/encounters/{encounter_id}/addenda")
            assert listed_resp.status_code == 200
            items = _addendum_items(listed_resp.json())
            assert any(
                item.get("id") == entry["id"]
                and item.get("reason") == S49_S4_REASON
                for item in items
            )

            other_denied = other.post(
                f"/api/v1/encounters/{encounter_id}/addenda",
                json=body_one,
                headers=mutation_headers(other, key="s49-s4c-add-other"),
            )
            assert other_denied.status_code == 403

            admin_denied = admin.post(
                f"/api/v1/encounters/{encounter_id}/addenda",
                json=body_one,
                headers=mutation_headers(admin, key="s49-s4c-add-admin"),
            )
            assert admin_denied.status_code == 403

            missing_reason = author.post(
                f"/api/v1/encounters/{encounter_id}/addenda",
                json={"correction_text": S49_S4_TEXT},
                headers=mutation_headers(author, key="s49-s4c-add-noreason"),
            )
            assert missing_reason.status_code == 422

            missing_text = author.post(
                f"/api/v1/encounters/{encounter_id}/addenda",
                json={"reason": S49_S4_REASON},
                headers=mutation_headers(author, key="s49-s4c-add-notext"),
            )
            assert missing_text.status_code == 422

            replay = author.post(
                f"/api/v1/encounters/{encounter_id}/addenda",
                json=body_one,
                headers=mutation_headers(author, key="s49-s4c-add-1"),
            )
            assert replay.status_code in (200, 201)
            assert _addendum_entry(replay.json())["id"] == entry["id"]

            conflicted = author.post(
                f"/api/v1/encounters/{encounter_id}/addenda",
                json={"reason": S49_S4_REASON, "correction_text": S49_S4_TEXT_TWO},
                headers=mutation_headers(author, key="s49-s4c-add-1"),
            )
            assert conflicted.status_code == 409

            body_two = {"reason": S49_S4_REASON, "correction_text": S49_S4_TEXT_TWO}
            second = author.post(
                f"/api/v1/encounters/{encounter_id}/addenda",
                json=body_two,
                headers=mutation_headers(author, key="s49-s4c-add-2"),
            )
            assert second.status_code == 201
            entry_two = _addendum_entry(second.json())
            assert entry_two["id"] != entry["id"]

            relisted = author.get(f"/api/v1/encounters/{encounter_id}/addenda")
            assert relisted.status_code == 200
            assert len(_addendum_items(relisted.json())) == 2

            after_dump, after_frozen = snapshot_dump(author, encounter_id)
            assert after_dump == before_dump
            assert after_frozen["snapshot_hash"] == signed_hash
            assert after_frozen["secondary_plan"]["text"] == SECONDARY_V1

        with TestClient(app) as anon:
            anon_denied = anon.post(
                f"/api/v1/encounters/{encounter_id}/addenda",
                json={"reason": S49_S4_REASON, "correction_text": S49_S4_TEXT},
            )
            assert anon_denied.status_code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
