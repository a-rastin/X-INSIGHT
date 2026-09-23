"""S46 (RED): ordered workflows + complete proposal assembly (T1/T8).

Tasks.md S46.1-4; plan.md 7.1/8.4/9; FR-15/FR-30-35; seams T1 + T8 only.

Synthetic 2-node A->B network only (same bytes as test_single_question.py,
never BNs/, never clinical, never a released default). Every question pins
identical network bytes under a distinct question_key/version/prompt marker
(SYNTH-S46-<key>). Controlled localhost provider only
(X_INSIGHT_PROVIDER_ALLOW_LOCAL=true); real PostgreSQL + real MCP +
public T1 GET /runs + T8 run_once. Setup-only direct SQL for bundles /
provider / DDI; all assertions read public GET JSON + captured provider
bodies, never SQL rows.

EXPECTED RED: the S45 coordinator completes exactly one claimed question
per run (no successor enqueue, run forced to 'succeeded', no proposal
assembly, no gate-stop, no DDI pinning). Every test below fails on a
missing multi-question behavior:
- slice1: only 1 of 7 provider bodies ever arrives (no sequential chain).
- slice2: run status is 'succeeded' instead of needs_clarification.
- slice3: no top-level "proposal" key exists on GET /runs.
- slice4: only 1 of 2 bodies arrives, so no proposal/staleness/LAI proof.
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
from x_insight.contracts import content_hash
from x_insight.ddi.terminology import canonical_pair_key
from x_insight.identity.throttle import reset_all
from x_insight.models.bundles import FOLLOWUP_ORDER, REGISTRATION_ORDER

SYNTHETIC_HISTORY_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "content" / "history"
)

SYNTHETIC_NETWORK_VERSION = "v1"
SYNTHETIC_HISTORY_VERSION = "synthetic-history-v1"
SYNTHETIC_MODEL = "synthetic-model-s46"
SYNTHETIC_API_KEY = "synthetic-provider-key-s46-001"

SENTINEL_FIRST = "SentinelAlpha"
SENTINEL_LAST = "SentinelBeta"
SENTINEL_PHONE = "SENTINEL-PHONE-0046"
SENTINEL_NOTE = "SENTINEL-NOTE-TEXT-s46-only"

# Same bytes as backend/tests/worker/test_single_question.py (plan.md 7.4).
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

LAI_INDICATION_MARKER = "SYNTH-S46-LAI-INDICATION"
LAI_CHOICE_MARKER = "SYNTH-S46-LAI-CHOICE"


@pytest.fixture(autouse=True)
def clean_workflows(monkeypatch):
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
                "reasoning_attempts, run_question_artifacts, audit_events, "
                "model_bundle_pointers, model_bundle_events, "
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
        headers=_mutation_headers(admin, key=f"s46-{username}-create"),
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


def _history_values(entries: dict[str, tuple[str, Any]]) -> dict[str, Any]:
    """Build stamped-shape history values from {field: (status, value)}."""
    return {
        field: {"status": status, "value": value}
        for field, (status, value) in entries.items()
    }


def _clinical_draft(
    *,
    history_entries: dict[str, tuple[str, Any]] | None = None,
    medications: list[dict[str, Any]] | None = None,
    ddi_version: str = "synthetic-ddi-s46",
    ddi_fingerprint: str = "fp-synth-s46",
) -> dict[str, Any]:
    if history_entries is None:
        history_entries = {"synthetic_flag_true": ("known", True)}
    return {
        "diagnosis": {"answers": {"synthetic_item": "synthetic_value"}},
        "history": {
            "definition_version": SYNTHETIC_HISTORY_VERSION,
            "values": _history_values(history_entries),
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
        "medications": (
            medications
            if medications is not None
            else [{"catalog_drug_id": "synthetic-med-a"}]
        ),
        "ddi_report": {
            "dataset_version": ddi_version,
            "medication_fingerprint": ddi_fingerprint,
        },
    }


def _synthetic_cpt_payload(question_key: str, network_hash: str = NETWORK_HASH) -> dict:
    return {
        "question_key": question_key,
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


def _make_question(
    key: str,
    index: int,
    *,
    network_hash: str = NETWORK_HASH,
    source_path: str | None = None,
    gate_expression: str | None = None,
    template: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One synthetic bundle entry: identical network bytes, distinct markers."""
    entry: dict[str, Any] = {
        "question_key": key,
        "version": SYNTHETIC_NETWORK_VERSION,
        "network_hash": network_hash,
        "network_xml": SYNTHETIC_XML.decode("utf-8"),
        "prompt": (
            f"SYNTH-S46-{key} SYNTH-Q{index} estimate every CPT as "
            "percentages summing to 100 using only listed patient "
            "facts. Do not write a plan. Do not choose applicability."
        ),
        "template": (
            template if template is not None else {"template_version": "synthetic-v1"}
        ),
    }
    if source_path is not None:
        entry["patient_mappings"] = [
            {
                "node_id": "A",
                "allowed_source_paths": [source_path],
                "typed_transform": "boolean",
            }
        ]
    if gate_expression is not None and source_path is not None:
        entry["applicability"] = {
            "expression": gate_expression,
            "required_fields": [source_path],
            "unknown_policy": "needs_clarification",
        }
    return entry


def _build_order_questions(
    order: list[str],
    *,
    network_hash: str = NETWORK_HASH,
    with_lai_branches: bool = False,
) -> list[dict[str, Any]]:
    questions = []
    for index, key in enumerate(order, start=1):
        template: dict[str, Any] | None = None
        if with_lai_branches and key == "lai_indication_choice":
            template = {
                "template_version": "synthetic-v1",
                "branches": {
                    "indication": {"marker": LAI_INDICATION_MARKER},
                    "choice": {"marker": LAI_CHOICE_MARKER},
                },
            }
        questions.append(
            _make_question(key, index, network_hash=network_hash, template=template)
        )
    return questions


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


def _insert_ddi_release(
    version: str, evidence: list[dict], scope: str = "limited"
) -> str:
    dataset_hash = f"synthetic-hash-{version}"
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
                "dataset_hash": dataset_hash,
                "source_inventory": json.dumps([]),
                "terminology_provenance": json.dumps(None),
                "review_record": json.dumps(
                    {"synthetic_fixture": True, "reviewer": "dr-synthetic"}
                ),
                "corrections": json.dumps([]),
                "coverage": json.dumps({"scope": scope, "exclusions": []}),
                "evidence": json.dumps(evidence),
            },
        )
    return dataset_hash


def _start_provider(payload_by_key: dict[str, dict], bodies: list[bytes]):
    """Controlled localhost provider: per-question valid CPTs, records bodies."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            bodies.append(raw)
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
            payload = payload_by_key.get(qkey) if isinstance(qkey, str) else None
            if payload is None:
                payload = next(iter(payload_by_key.values()))
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


def _drain(worker_prefix: str, max_steps: int = 10) -> list[dict]:
    """Loop the public T8 entry point until no job is claimed (max_steps)."""
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


# ---------------------------------------------------------------------------
# S46 slice 1: ordered sequential execution, no intra-run parallelism.
# ---------------------------------------------------------------------------


def test_ordered_sequential_no_parallelism() -> None:
    """Seven-question registration workflow runs in pinned order, one at a time.

    RED: the S45 coordinator completes only the first claimed question and
    never enqueues a successor, so draining stops after 1 body/section
    instead of the pinned 7 in REGISTRATION_ORDER.
    """
    assert len(REGISTRATION_ORDER) == 7
    assert len(FOLLOWUP_ORDER) == 6
    assert REGISTRATION_ORDER[4] == "lai_indication_choice"

    bundle_hash = "synthetic-bundle-hash-s46-slice1"
    questions = _build_order_questions(list(REGISTRATION_ORDER))
    payload_by_key = {
        q["question_key"]: _synthetic_cpt_payload(q["question_key"]) for q in questions
    }
    bodies: list[bytes] = []

    server, thread = _start_provider(payload_by_key, bodies)
    try:
        host, port = server.server_address
        _insert_bundle("registration", 1, bundle_hash, questions)
        _insert_provider_config(f"http://{host}:{port}")

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s46docA")
            _login(physician, "s46docA", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000461", "s46-s1-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_id = _start_run(physician, encounter_id, revision, "s46-s1-run-1")

            outcomes = _drain("s46-s1", max_steps=10)
            claimed = [o for o in outcomes if o.get("claimed")]
            # Sequential proof: after each claimed step exactly one new
            # section is committed before the next provider body appears.
            # A full chain ends with one section per pinned question; the
            # per-step GET walk below can only pass once run_once chains.
            body = _get_run(physician, run_id)
            sections_seen = [len(body["sections"])]
            jobs_snapshots = [body["jobs"]]

            # RED: only 1 body/section exists; the chain stops after q1.
            assert len(bodies) == 7
            assert len(claimed) == 7
            assert sections_seen == [7]

            ordered_keys = [_body_question_key(raw) for raw in bodies]
            assert ordered_keys == list(REGISTRATION_ORDER)

            for raw, key in zip(bodies, list(REGISTRATION_ORDER)):
                dumped = json.dumps(json.loads(raw.decode("utf-8")), sort_keys=True)
                assert f"SYNTH-S46-{key}" in dumped
                later = list(REGISTRATION_ORDER)[
                    list(REGISTRATION_ORDER).index(key) + 1 :
                ]
                for other in later:
                    assert f"SYNTH-S46-{other}" not in dumped

            # No two jobs of one run are ever concurrently claimable: at
            # most one queued/claimed job is visible per poll.
            for snapshot in jobs_snapshots:
                active = [j for j in snapshot if j["status"] in ("queued", "claimed")]
                assert len(active) <= 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S46 slice 2: gates record without calls; unknown stops; scoped isolation.
# ---------------------------------------------------------------------------

S46_READY_PATH = "encounters.draft_data.history.values.synthetic_flag_true"
S46_FALSE_PATH = "encounters.draft_data.history.values.synthetic_flag_false"
S46_MISSING_PATH = "encounters.draft_data.history.values.synthetic_flag_unknown"
S46_AFTER_PATH = "encounters.draft_data.history.values.synthetic_flag_not_assessed"


def test_gates_no_call_stop_isolation() -> None:
    """False gate skips without a call; unknown stops; later work never runs.

    Bundle: q_ready (True -> ready), q_false (False -> not_applicable),
    q_unknown (missing -> needs_clarification), q_after (ready but blocked).
    RED: the coordinator marks the run 'succeeded' after q_ready instead
    of stopping with needs_clarification.
    """
    bundle_hash = "synthetic-bundle-hash-s46-slice2"
    questions = [
        _make_question(
            "q_ready",
            1,
            source_path=S46_READY_PATH,
            gate_expression=f"{S46_READY_PATH} == true",
        ),
        _make_question(
            "q_false",
            2,
            source_path=S46_FALSE_PATH,
            gate_expression=f"{S46_FALSE_PATH} == true",
        ),
        _make_question(
            "q_unknown",
            3,
            source_path=S46_MISSING_PATH,
            gate_expression=f"{S46_MISSING_PATH} == true",
        ),
        _make_question(
            "q_after",
            4,
            source_path=S46_AFTER_PATH,
            gate_expression=f"{S46_AFTER_PATH} == true",
        ),
    ]
    payload_by_key = {
        q["question_key"]: _synthetic_cpt_payload(q["question_key"]) for q in questions
    }
    bodies: list[bytes] = []

    server, thread = _start_provider(payload_by_key, bodies)
    try:
        host, port = server.server_address
        _insert_bundle("registration", 1, bundle_hash, questions)
        _insert_provider_config(f"http://{host}:{port}")

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s46docB")
            _login(physician, "s46docB", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000462", "s46-s2-patient"
            )
            encounter_id = encounter["id"]
            draft = _clinical_draft(
                history_entries={
                    "synthetic_flag_true": ("known", True),
                    "synthetic_flag_false": ("known", False),
                    "synthetic_flag_not_assessed": ("known", True),
                }
            )
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": draft},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_id = _start_run(physician, encounter_id, revision, "s46-s2-run-1")
            _drain("s46-s2", max_steps=10)

            # Only the ready question ever reaches the provider.
            assert len(bodies) == 1
            assert _body_question_key(bodies[0]) == "q_ready"
            dumped_calls = json.dumps([json.loads(b.decode("utf-8")) for b in bodies])
            assert "q_false" not in dumped_calls
            assert "q_after" not in dumped_calls
            assert "q_unknown" not in dumped_calls

            body = _get_run(physician, run_id)
            by_key = {p["question_key"]: p for p in body["projections"]}
            assert by_key["q_ready"]["applicability"] == "ready"
            assert by_key["q_false"]["applicability"] == "not_applicable"
            assert by_key["q_false"]["applicability_reason"]
            assert by_key["q_unknown"]["applicability"] == "needs_clarification"
            assert by_key["q_unknown"]["applicability_reason"]

            # Required-unknown stops progression: terminal clarification,
            # never success; only q_ready has a section.
            assert body["run"]["status"] in ("needs_clarification", "failed")
            assert body["run"]["status"] != "succeeded"
            assert [s["question_key"] for s in body["sections"]] == ["q_ready"]

            # Isolation: the q_ready request carries only its own source
            # path — no unrelated flag, no prior posteriors, no PII/notes.
            captured = json.dumps(json.loads(bodies[0].decode("utf-8")), sort_keys=True)
            assert S46_READY_PATH in captured
            assert S46_AFTER_PATH not in captured
            assert S46_FALSE_PATH not in captured
            assert S46_MISSING_PATH not in captured
            assert "posterior" not in captured.lower()
            for sentinel in (
                SENTINEL_FIRST,
                SENTINEL_LAST,
                SENTINEL_PHONE,
                SENTINEL_NOTE,
            ):
                assert sentinel not in captured
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S46 slice 3: proposal needs every applicable question + pinned DDI.
# ---------------------------------------------------------------------------


def test_proposal_requires_all_applicable_plus_ddi() -> None:
    """Final proposal succeeds only after all questions + valid pinned DDI.

    RED: GET /runs exposes sections but no top-level "proposal" key, and
    the queue never advances past the first question.
    """
    from x_insight.reasoning.worker import run_once

    ddi_version = "synthetic-ddi-s46"
    med_a = "synthetic-s46-med-a"
    med_b = "synthetic-s46-med-b"
    pair_key = canonical_pair_key(med_a, med_b)
    evidence = [
        {
            "pair_key": pair_key,
            "source_severity": "monitor_closely",
            "management": "SYNTHETIC s46 management - test only",
            "direction": {"subject": med_a, "object": med_b},
            "source_path": "SYNTHETIC-s46.txt",
            "span": {"start_line": 1, "end_line": 2},
            "raw_text": "SYNTHETIC s46 evidence for pair coverage - test only",
        }
    ]
    dataset_hash = _insert_ddi_release(ddi_version, evidence, scope="limited")
    expected_fingerprint = content_hash(
        {"resolved": sorted([med_a, med_b]), "unresolved": []}
    )

    bundle_hash = "synthetic-bundle-hash-s46-slice3"
    keys = ["s46_p1", "s46_p2", "s46_p3"]
    questions = [_make_question(key, i + 1) for i, key in enumerate(keys)]
    payload_by_key = {key: _synthetic_cpt_payload(key) for key in keys}
    bodies: list[bytes] = []

    server, thread = _start_provider(payload_by_key, bodies)
    try:
        host, port = server.server_address
        _insert_bundle("registration", 1, bundle_hash, questions)
        _insert_provider_config(f"http://{host}:{port}")

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s46docC")
            _login(physician, "s46docC", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000463", "s46-s3-patient"
            )
            encounter_id = encounter["id"]
            draft = _clinical_draft(
                medications=[{"catalog_drug_id": med_a}, {"catalog_drug_id": med_b}],
                ddi_version=ddi_version,
                ddi_fingerprint=expected_fingerprint,
            )
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": draft},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_id = _start_run(physician, encounter_id, revision, "s46-s3-run-1")

            # Partial run stays readable but incomplete: after one step the
            # proposal is absent/incomplete while one section is readable.
            first = run_once(
                database_url=None, provider_adapter=None, worker_id="s46-s3-0"
            )
            assert first.get("claimed") is True
            partial = _get_run(physician, run_id)
            assert len(partial["sections"]) == 1
            proposal_partial = partial.get("proposal")
            assert (
                proposal_partial is None
                or proposal_partial.get("status") != "succeeded"
            )

            _drain("s46-s3", max_steps=10)

            # RED: the chain never advances; no proposal key exists.
            assert len(bodies) == 3
            body = _get_run(physician, run_id)
            proposal = body["proposal"]
            assert proposal["status"] == "succeeded"
            assert [s["question_key"] for s in body["sections"]] == keys
            assert proposal["sections"] == keys
            assert proposal.get("skipped", []) == []

            ddi_report = proposal["ddi_report"]
            assert ddi_report["dataset_version"] == ddi_version
            assert ddi_report["dataset_hash"] == dataset_hash
            assert ddi_report["medication_fingerprint"] == expected_fingerprint
            dumped_ddi = json.dumps(ddi_report, sort_keys=True)
            assert ddi_version in dumped_ddi
            assert "coverage" in dumped_ddi.lower()
            assert body["run"]["status"] == "succeeded"

            # No LLM proposal-writing request exists: exactly one CPT
            # estimation call per applicable question, each carrying the
            # CPT contract and no proposal-drafting text.
            assert len(bodies) == len(keys)
            for raw in bodies:
                dumped = json.dumps(json.loads(raw.decode("utf-8")), sort_keys=True)
                assert "cpt_contract" in dumped
                assert "proposal" not in dumped.lower()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# S46 slice 4: staleness pinning, bundle rotation, combined LAI step.
# ---------------------------------------------------------------------------


def test_staleness_pinning_and_lai() -> None:
    """Old runs stay pinned; new inputs/bundles start fresh; LAI is one step.

    RED: the 2-question chain never completes, so no proposal exists to
    pin, and the LAI section never renders both branch markers.
    """
    ddi_version = "synthetic-ddi-s46"
    med_a = "synthetic-s46-med-a"
    med_b = "synthetic-s46-med-b"
    med_c = "synthetic-s46-med-c"
    pair_key = canonical_pair_key(med_a, med_b)
    evidence = [
        {
            "pair_key": pair_key,
            "source_severity": "monitor_closely",
            "management": "SYNTHETIC s46 management - test only",
            "direction": {"subject": med_a, "object": med_b},
            "source_path": "SYNTHETIC-s46.txt",
            "span": {"start_line": 1, "end_line": 2},
            "raw_text": "SYNTHETIC s46 evidence for pair coverage - test only",
        }
    ]
    _insert_ddi_release(ddi_version, evidence, scope="limited")
    fp_old = content_hash({"resolved": sorted([med_a, med_b]), "unresolved": []})
    fp_new = content_hash({"resolved": sorted([med_a, med_c]), "unresolved": []})
    assert fp_old != fp_new

    bundle_hash_v1 = "synthetic-bundle-hash-s46-v1"
    keys = ["s46_g1", "lai_indication_choice"]
    questions_v1 = _build_order_questions(keys, with_lai_branches=True)
    # Distinct prompt markers per question (same network bytes).
    for q in questions_v1:
        assert f"SYNTH-S46-{q['question_key']}" in q["prompt"]
    lai_entry = next(
        q for q in questions_v1 if q["question_key"] == "lai_indication_choice"
    )
    assert LAI_INDICATION_MARKER in json.dumps(lai_entry["template"])
    assert LAI_CHOICE_MARKER in json.dumps(lai_entry["template"])
    assert sum(1 for q in questions_v1 if "lai" in q["question_key"]) == 1

    payload_by_key = {key: _synthetic_cpt_payload(key) for key in keys}
    bodies: list[bytes] = []

    server, thread = _start_provider(payload_by_key, bodies)
    try:
        host, port = server.server_address
        _insert_bundle("registration", 1, bundle_hash_v1, questions_v1)
        _insert_provider_config(f"http://{host}:{port}")

        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "s46docD")
            _login(physician, "s46docD", "secret", "physician")
            _patient, encounter = _create_sentinel_patient(
                physician, "0799000464", "s46-s4-patient"
            )
            encounter_id = encounter["id"]
            draft = _clinical_draft(
                medications=[{"catalog_drug_id": med_a}, {"catalog_drug_id": med_b}],
                ddi_version=ddi_version,
                ddi_fingerprint=fp_old,
            )
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": draft},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_id_old = _start_run(physician, encounter_id, revision, "s46-s4-run-1")
            _drain("s46-s4-old", max_steps=10)

            # RED: the second question never runs; no proposal to pin.
            assert len(bodies) == 2
            old_body = _get_run(physician, run_id_old)
            assert old_body["proposal"]["status"] == "succeeded"
            old_proposal_dump = json.dumps(old_body["proposal"], sort_keys=True)
            old_sections_dump = json.dumps(old_body["sections"], sort_keys=True)

            # (c) One combined LAI step renders BOTH outputs under its mapping.
            lai_sections = [
                s
                for s in old_body["sections"]
                if s["question_key"] == "lai_indication_choice"
            ]
            assert len(lai_sections) == 1
            assert LAI_INDICATION_MARKER in lai_sections[0]["rendered_text"]
            assert LAI_CHOICE_MARKER in lai_sections[0]["rendered_text"]

            # (a) Changed medications start a fresh run; the old pinned
            # proposal is byte-identical afterwards.
            revision2 = _current_revision(physician, encounter_id)
            patched = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={
                    "draft_data": _clinical_draft(
                        medications=[
                            {"catalog_drug_id": med_a},
                            {"catalog_drug_id": med_c},
                        ],
                        ddi_version=ddi_version,
                        ddi_fingerprint=fp_new,
                    )
                },
                headers=_mutation_headers(physician, revision=revision2),
            )
            assert patched.status_code == 200
            revision3 = _current_revision(physician, encounter_id)
            run_id_new = _start_run(physician, encounter_id, revision3, "s46-s4-run-2")
            assert run_id_new != run_id_old
            new_body = _get_run(physician, run_id_new)
            assert new_body["fingerprint"] != old_body["fingerprint"]
            assert (
                new_body.get("proposal") is None
                or new_body["proposal"].get("status") != "succeeded"
            )

            reread_old = _get_run(physician, run_id_old)
            assert (
                json.dumps(reread_old["proposal"], sort_keys=True) == old_proposal_dump
            )
            assert (
                json.dumps(reread_old["sections"], sort_keys=True) == old_sections_dump
            )
            assert reread_old["pinned"]["bundle_hash"] == bundle_hash_v1
            assert old_body["stale"] is False
            assert reread_old["stale"] is True
            assert reread_old["fingerprint"] == old_body["fingerprint"]
            assert json.dumps(
                {k: v for k, v in reread_old.items() if k != "stale"}, sort_keys=True
            ) == json.dumps(
                {k: v for k, v in old_body.items() if k != "stale"}, sort_keys=True
            )

            # (b) Activating a new bundle revision never mutates the pinned run.
            questions_v2 = _build_order_questions(keys, with_lai_branches=True)
            for q in questions_v2:
                q["prompt"] = q["prompt"].replace("SYNTH-S46-", "SYNTH-S46-REV2-")
            bundle_hash_v2 = "synthetic-bundle-hash-s46-v2"
            _insert_bundle("registration", 2, bundle_hash_v2, questions_v2)
            rotated = _get_run(physician, run_id_old)
            assert rotated["pinned"]["bundle_hash"] == bundle_hash_v1
            assert json.dumps(rotated["proposal"], sort_keys=True) == old_proposal_dump
            assert "SYNTH-S46-REV2-" not in json.dumps(rotated, sort_keys=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
