"""S40 slice 1 (RED): freeze analysis snapshot + project one question (T1).

Slice-1 scope ONLY (tasks.md S40.1): starting a run from a saved
author-owned revision freezes allowed clinical facts plus all selected
version references, while shared notes and patient names/ID/phone stay
absent from the model-facing projection. Invalid/stale revisions fail
without partial snapshot creation. Slices 2-4 (per-variable typed
projection/mapping rejection, fingerprint-vs-note staleness, gate
evaluation) are NOT tested here.

Proposed minimal run contract for the backend agent (no extra seams):

- POST /api/v1/encounters/{encounter_id}/runs
  body: {"encounter_revision": int} (nothing else in slice 1;
  warning_acknowledgments arrive with a later slice).
  Headers: Idempotency-Key REQUIRED (absent/invalid -> 422, same
  convention as POST /patients and follow-up create) AND If-Match
  REQUIRED (must equal the current encounter revision; mismatch,
  including absent, -> 412, same convention as PATCH /encounters).
  The body encounter_revision must ALSO equal the current revision;
  either header/body staleness -> 412.
  Success: 202 {"schema_version": 1, "run_id": uuid, "revision": int,
  "status": str, "questions": [...]} (status/progress values and queue
  execution belong to S44; slice 1 only needs the keys present).
  Errors: 401 anonymous (before CSRF), 403 non-author (administrator
  included: shared reads never grant run creation), 404 missing
  encounter, 409 terminal/archived/wrong state (discarded/signed;
  archived via patients.archived even though no archive route exists
  until S51) or Idempotency-Key reuse with a different body, 412 stale
  revision, 422 invalid body/missing key. Check precedence for the
  tests below: session -> existence -> ownership -> terminal state ->
  revision match -> body shape. One transaction: no partial snapshot
  row/projection on any failure.
- GET /api/v1/runs/{run_id}
  Success: 200 {"schema_version": 1, "run": {...},
  "snapshot_hash": str, "fingerprint": str, "projections": [...],
  "pinned": {...}}. snapshot_hash covers the full frozen snapshot
  (facts + pins); fingerprint is the plan 4.2 analysis fingerprint
  (analytical facts + reconciled medications + pinned content, driving
  later staleness/signing checks). projections is the per-question list;
  each entry carries at least question_key + projection_hash. pinned
  carries at least bundle_hash (+ history/ddi versions below);
  provider/assessment/engine pins are backend-owned (nullable while
  unconfigured) and asserted only for presence of the dict here.
  Errors: 401 anonymous, 403 non-author, 404 missing run.

Run start requires draft state only: a registration draft (S07/S14
states) is enough; no signed baseline is needed to freeze a snapshot.

Synthetic-bundle choice (test-only, never a production default): the
fixture inserts ONE synthetic registration pointer/event row directly
into model_bundle_pointers/model_bundle_events (workflow
"registration", revision 1, bundle_hash
"synthetic-bundle-hash-s40-slice1", pins JSON naming one synthetic
question "synthetic_example"). This is the smallest honest setup that
proves version pinning end to end: GET /runs must echo the pinned
bundle_hash. Real reviewed bundles arrive via S24/S39; until then the
server must NOT fall back to an implicit default bundle (missing
pointer -> 409).

Frozen facts exercised here (all synthetic): diagnosis answers,
history values, adverse effects, drug-only medications, ddi_report
reference, patient clinical_status + encounter kind. Mixed-content
sentinels (letters-only sentinel names, ten-digit ID, phone text, note
text) must appear NOWHERE in the GET /runs JSON dump.
"""

from __future__ import annotations

import json
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

SENTINEL_FIRST = "SentinelAlpha"
SENTINEL_LAST = "SentinelBeta"
SENTINEL_PID = "0799000041"
SENTINEL_PHONE = "SENTINEL-PHONE-0001"
SENTINEL_NOTE = "SENTINEL-NOTE-TEXT-s40-slice1-only"

SYNTHETIC_BUNDLE_HASH = "synthetic-bundle-hash-s40-slice1"
SYNTHETIC_QUESTION = "synthetic_example"
SYNTHETIC_HISTORY_VERSION = "synthetic-history-v1"
SYNTHETIC_DDI_VERSION = "synthetic-ddi-s40-v1"
SYNTHETIC_MEDICATION_FINGERPRINT = "fp-synth-s40-slice1"


@pytest.fixture(autouse=True)
def clean_snapshots(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, runs, run_questions, audit_events, "
                "model_bundle_pointers, model_bundle_events"
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
        headers=_mutation_headers(admin, key=f"s40-{username}-create"),
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
                "synthetic_flag_false": {"status": "known", "value": False},
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
            {"unknown_label": "synthetic-unknown-x"},
        ],
        "ddi_report": {
            "dataset_version": SYNTHETIC_DDI_VERSION,
            "medication_fingerprint": SYNTHETIC_MEDICATION_FINGERPRINT,
        },
    }


def _insert_synthetic_bundle():
    pins = {
        "questions": [
            {
                "question_key": SYNTHETIC_QUESTION,
                "version": "synthetic-v1",
                "network_hash": "synthetic-network-hash-s40-slice1",
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


def _current_revision(physician, encounter_id):
    fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
    assert fetched.status_code == 200
    return int(fetched.json()["encounter"]["revision"])


def test_run_freezes_clinical_facts_and_excludes_pii_and_notes():
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "snapdocA")
        _login(physician, "snapdocA", "secret", "physician")
        _patient, encounter = _create_sentinel_patient(
            physician, SENTINEL_PID, "s40-s1-patient"
        )
        encounter_id = encounter["id"]

        saved = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": _clinical_draft()},
            headers=_mutation_headers(physician, revision=encounter["revision"]),
        )
        assert saved.status_code == 200

        noted = physician.post(
            f"/api/v1/encounters/{encounter_id}/notes",
            json={"page": "history", "text": SENTINEL_NOTE},
            headers=_mutation_headers(physician, key="s40-s1-note-1"),
        )
        assert noted.status_code == 201

        _insert_synthetic_bundle()
        revision = _current_revision(physician, encounter_id)

        started = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s40-s1-run-1", revision=revision
            ),
        )
        assert started.status_code == 202
        created = started.json()
        run_id = created["run_id"]
        uuid.UUID(run_id)
        assert created["revision"] == revision
        assert isinstance(created.get("status"), str)
        assert isinstance(created.get("questions"), list)
        assert len(created["questions"]) >= 1

        fetched = physician.get(f"/api/v1/runs/{run_id}")
        assert fetched.status_code == 200
        body = fetched.json()
        assert isinstance(body.get("snapshot_hash"), str) and body["snapshot_hash"]
        assert isinstance(body.get("fingerprint"), str) and body["fingerprint"]
        pinned = body.get("pinned")
        assert isinstance(pinned, dict)
        assert pinned.get("bundle_hash") == SYNTHETIC_BUNDLE_HASH
        assert pinned.get("history_definition_version") == SYNTHETIC_HISTORY_VERSION
        assert pinned.get("ddi_dataset_version") == SYNTHETIC_DDI_VERSION
        projections = body.get("projections")
        assert isinstance(projections, list) and len(projections) >= 1
        assert all(
            isinstance(item, dict)
            and item.get("question_key")
            and item.get("projection_hash")
            for item in projections
        )

        dumped = json.dumps(body)
        assert SYNTHETIC_HISTORY_VERSION in dumped
        assert "synthetic-med-a" in dumped
        assert SYNTHETIC_MEDICATION_FINGERPRINT in dumped
        for sentinel in (
            SENTINEL_FIRST,
            SENTINEL_LAST,
            SENTINEL_PID,
            SENTINEL_PHONE,
            SENTINEL_NOTE,
        ):
            assert sentinel not in dumped

        refetched = physician.get(f"/api/v1/runs/{run_id}")
        assert refetched.status_code == 200
        assert refetched.json()["snapshot_hash"] == body["snapshot_hash"]
        assert refetched.json()["fingerprint"] == body["fingerprint"]


def test_run_start_guards_auth_ownership_and_body():
    with (
        TestClient(app) as admin,
        TestClient(app) as author,
        TestClient(app) as other,
    ):
        _login(admin)
        _make_physician(admin, "snapdocB1")
        _make_physician(admin, "snapdocB2")
        _login(author, "snapdocB1", "secret", "physician")
        _login(other, "snapdocB2", "secret", "physician")
        _patient, encounter = _create_sentinel_patient(
            author, "0799000042", "s40-s1-guard-patient"
        )
        encounter_id = encounter["id"]
        saved = author.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": _clinical_draft()},
            headers=_mutation_headers(author, revision=encounter["revision"]),
        )
        assert saved.status_code == 200
        _insert_synthetic_bundle()
        revision = _current_revision(author, encounter_id)

        with TestClient(app) as anon:
            denied = anon.post(
                f"/api/v1/encounters/{encounter_id}/runs",
                json={"encounter_revision": revision},
            )
            assert denied.status_code == 401

        forbidden_other = other.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(other, key="s40-s1-guard-other", revision=revision),
        )
        assert forbidden_other.status_code == 403

        forbidden_admin = admin.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(admin, key="s40-s1-guard-admin", revision=revision),
        )
        assert forbidden_admin.status_code == 403

        missing_id = "00000000-0000-0000-0000-000000000000"
        missing = author.post(
            f"/api/v1/encounters/{missing_id}/runs",
            json={"encounter_revision": 1},
            headers=_mutation_headers(author, key="s40-s1-guard-missing", revision=1),
        )
        assert missing.status_code == 404

        no_key = author.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(author, revision=revision),
        )
        assert no_key.status_code == 422

        empty_body = author.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={},
            headers=_mutation_headers(
                author, key="s40-s1-guard-empty", revision=revision
            ),
        )
        assert empty_body.status_code == 422

        wrong_type = author.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": "not-an-int"},
            headers=_mutation_headers(
                author, key="s40-s1-guard-type", revision=revision
            ),
        )
        assert wrong_type.status_code == 422

        started = author.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(author, key="s40-s1-guard-run", revision=revision),
        )
        assert started.status_code == 202
        run_id = started.json()["run_id"]

        with TestClient(app) as anon:
            assert anon.get(f"/api/v1/runs/{run_id}").status_code == 401
        assert other.get(f"/api/v1/runs/{run_id}").status_code == 403
        assert (
            author.get(f"/api/v1/runs/{missing_id}").status_code == 404
        )


def test_stale_or_invalid_revision_fails_without_partial_snapshot():
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "snapdocC")
        _login(physician, "snapdocC", "secret", "physician")
        _patient, encounter = _create_sentinel_patient(
            physician, "0799000043", "s40-s1-stale-patient"
        )
        encounter_id = encounter["id"]
        saved = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": _clinical_draft()},
            headers=_mutation_headers(physician, revision=encounter["revision"]),
        )
        assert saved.status_code == 200
        stale_revision = int(saved.json()["encounter"]["revision"])

        touched = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={
                "draft_data": {
                    **_clinical_draft(),
                    "diagnosis": {"answers": {"synthetic_item": "synthetic_edited"}},
                }
            },
            headers=_mutation_headers(physician, revision=stale_revision),
        )
        assert touched.status_code == 200
        current = int(touched.json()["encounter"]["revision"])
        assert current == stale_revision + 1
        _insert_synthetic_bundle()

        stale = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": stale_revision},
            headers=_mutation_headers(
                physician, key="s40-s1-stale-1", revision=stale_revision
            ),
        )
        assert stale.status_code == 412

        invalid = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": "not-an-int"},
            headers=_mutation_headers(
                physician, key="s40-s1-stale-2", revision=current
            ),
        )
        assert invalid.status_code == 422

        # No partial snapshot leaked: unknown run IDs stay 404 ...
        unknown_id = "00000000-0000-0000-0000-000000000000"
        assert physician.get(f"/api/v1/runs/{unknown_id}").status_code == 404

        # ... and a correct retry still freezes cleanly.
        retried = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": current},
            headers=_mutation_headers(
                physician, key="s40-s1-stale-3", revision=current
            ),
        )
        assert retried.status_code == 202
        run_id = retried.json()["run_id"]
        assert physician.get(f"/api/v1/runs/{run_id}").status_code == 200

        # Terminal state conflicts even at the current revision.
        discarded = physician.post(
            f"/api/v1/encounters/{encounter_id}/discard",
            json={"confirm": True},
            headers=_mutation_headers(physician, revision=current),
        )
        assert discarded.status_code == 200
        terminal_revision = int(discarded.json()["encounter"]["revision"])
        conflicted = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": terminal_revision},
            headers=_mutation_headers(
                physician, key="s40-s1-stale-4", revision=terminal_revision
            ),
        )
        assert conflicted.status_code == 409


# ---------------------------------------------------------------------------
# S40 slice 2 (RED): per-question typed projection + mapping rejection (T1).
#
# Test-only contract: S40 bundle pins JSON is the mapping carrier. Real
# registry pins (S24) lack patient_mappings; S40 synthetic pins may embed
# patient_mappings for the synthetic question only. This is never a
# production default. Mapping shape mirrors question_packages.py
# (node_id, allowed_source_paths, typed_transform, time_window, usage,
# missing_policy); prompt wording never authorizes extra sources.
# ---------------------------------------------------------------------------

SYNTHETIC_BUNDLE_HASH_SLICE2 = "synthetic-bundle-hash-s40-slice2"
SYNTHETIC_NETWORK_HASH_SLICE2 = "synthetic-network-hash-s40-slice2"

SLICE2_PID_PROJECTION = "0799000051"
SLICE2_PID_REJECTION = "0799000052"

UNRELATED_HISTORY_SENTINEL = "synthetic_flag_false"
UNRELATED_MED_SENTINEL = "synthetic-med-a"
SENTINEL_NOTE_SLICE2 = "SENTINEL-NOTE-TEXT-s40-slice2-only"

EXPECTED_SLICE2_NODES = frozenset(
    {"syn_known", "syn_missing", "syn_not_assessed", "syn_conflict"}
)


def _mapping_draft_with_states():
    """Synthetic draft covering observed/missing/not_assessed/conflict.

    History uses only released synthetic-history-v1 statuses
    (known/unknown/not_assessed). Conflict is carried in the verbatim
    top-level ``synthetic_conflict`` marker (PATCH stores unknown
    top-level keys verbatim), so the test does not invent an invalid
    history status. ``synthetic_flag_false`` is present but deliberately
    unmapped: it is the unrelated history field that must never appear
    in variables[].
    """
    return {
        "diagnosis": {"answers": {"synthetic_item": "synthetic_value"}},
        "history": {
            "definition_version": SYNTHETIC_HISTORY_VERSION,
            "values": {
                "synthetic_flag_true": {"status": "known", "value": True},
                "synthetic_flag_unknown": {"status": "unknown", "value": None},
                "synthetic_flag_not_assessed": {
                    "status": "not_assessed",
                    "value": None,
                },
                UNRELATED_HISTORY_SENTINEL: {"status": "known", "value": False},
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
            {"unknown_label": "synthetic-unknown-x"},
        ],
        "ddi_report": {
            "dataset_version": SYNTHETIC_DDI_VERSION,
            "medication_fingerprint": SYNTHETIC_MEDICATION_FINGERPRINT,
        },
        "synthetic_conflict": {"status": "conflict", "candidates": [True, False]},
    }


def _valid_slice2_mappings():
    return [
        {
            "node_id": "syn_known",
            "allowed_source_paths": [
                "encounters.draft_data.history.values.synthetic_flag_true"
            ],
            "typed_transform": "boolean",
            "time_window": "current",
            "usage": "observation",
            "missing_policy": "missing",
        },
        {
            "node_id": "syn_missing",
            "allowed_source_paths": [
                "encounters.draft_data.history.values.synthetic_flag_unknown"
            ],
            "typed_transform": "boolean",
            "time_window": "current",
            "usage": "observation",
            "missing_policy": "missing",
        },
        {
            "node_id": "syn_not_assessed",
            "allowed_source_paths": [
                "encounters.draft_data.history.values.synthetic_flag_not_assessed"
            ],
            "typed_transform": "boolean",
            "time_window": "current",
            "usage": "observation",
            "missing_policy": "missing",
        },
        {
            "node_id": "syn_conflict",
            "allowed_source_paths": ["encounters.draft_data.synthetic_conflict"],
            "typed_transform": "boolean",
            "time_window": "current",
            "usage": "observation",
            "missing_policy": "missing",
        },
    ]


def _insert_mapping_bundle(mappings, prompt=None):
    """Insert the slice-2 synthetic bundle pointer (test-only carrier)."""
    question = {
        "question_key": SYNTHETIC_QUESTION,
        "version": "synthetic-v1",
        "network_hash": SYNTHETIC_NETWORK_HASH_SLICE2,
        "patient_mappings": mappings,
    }
    if prompt is not None:
        question["prompt"] = prompt
    pins = {"questions": [question]}
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO model_bundle_pointers "
                "(workflow, revision, bundle_hash, pins) "
                "VALUES ('registration', 1, :hash, CAST(:pins AS jsonb)) "
                "ON CONFLICT (workflow) DO UPDATE SET revision = 1, "
                "bundle_hash = :hash, pins = CAST(:pins AS jsonb)"
            ),
            {"hash": SYNTHETIC_BUNDLE_HASH_SLICE2, "pins": json.dumps(pins)},
        )
        conn.execute(
            text(
                "INSERT INTO model_bundle_events "
                "(workflow, revision, bundle_hash, pins, action) "
                "VALUES ('registration', 1, :hash, CAST(:pins AS jsonb), "
                "'activate') ON CONFLICT (workflow, revision) DO NOTHING"
            ),
            {"hash": SYNTHETIC_BUNDLE_HASH_SLICE2, "pins": json.dumps(pins)},
        )


def test_projection_exact_variables_slice2():
    """Projection exactness: only mapped nodes with typed state (RED).

    Pins carry patient_mappings (test-only carrier). Draft holds known /
    unknown / not_assessed history plus a verbatim synthetic_conflict
    marker and one unmapped history field (synthetic_flag_false).

    Expected per-question projection schema (backend contract):
    variables is a LIST; each entry has exactly
    {node_id, patient_type, status, value, source_path, source_revision}
    with status in {observed, missing, not_assessed, conflict}, value
    explicit null when unavailable, source_path equal to the declared
    allowed_source_path, and source_revision equal to the frozen
    encounter revision (int). Only the four declared nodes appear;
    unrelated history / meds stay out of variables[]; notes and PII stay
    out of the whole GET /runs body.

    RED: current build_projections returns variables:{} (dict, empty),
    so the list/shape assertions fail.
    """
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "snapdocS2A")
        _login(physician, "snapdocS2A", "secret", "physician")
        _patient, encounter = _create_sentinel_patient(
            physician, SLICE2_PID_PROJECTION, "s40-s2-proj-patient"
        )
        encounter_id = encounter["id"]
        saved = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": _mapping_draft_with_states()},
            headers=_mutation_headers(physician, revision=encounter["revision"]),
        )
        assert saved.status_code == 200
        noted = physician.post(
            f"/api/v1/encounters/{encounter_id}/notes",
            json={"page": "history", "text": SENTINEL_NOTE_SLICE2},
            headers=_mutation_headers(physician, key="s40-s2-proj-note-1"),
        )
        assert noted.status_code == 201

        _insert_mapping_bundle(_valid_slice2_mappings())
        revision = _current_revision(physician, encounter_id)
        started = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s40-s2-proj-run-1", revision=revision
            ),
        )
        assert started.status_code == 202
        run_id = started.json()["run_id"]

        fetched = physician.get(f"/api/v1/runs/{run_id}")
        assert fetched.status_code == 200
        body = fetched.json()
        projections = body.get("projections")
        assert isinstance(projections, list) and len(projections) >= 1
        entry = next(
            item
            for item in projections
            if item.get("question_key") == SYNTHETIC_QUESTION
        )
        projection = entry.get("projection")
        assert isinstance(projection, dict)
        variables = projection.get("variables")
        # RED: currently {} (dict), not a typed list.
        assert isinstance(variables, list), "variables must be a typed list"
        assert len(variables) == 4
        by_node = {item["node_id"]: item for item in variables}
        assert set(by_node) == set(EXPECTED_SLICE2_NODES)
        for item in variables:
            assert set(item) == {
                "node_id",
                "patient_type",
                "status",
                "value",
                "source_path",
                "source_revision",
            }
            assert item["status"] in {
                "observed",
                "missing",
                "not_assessed",
                "conflict",
            }
            assert item["patient_type"] == "boolean"
            assert item["source_revision"] == revision
            if item["status"] == "observed":
                assert item["value"] is True
            else:
                assert item["value"] is None
        assert by_node["syn_known"]["status"] == "observed"
        assert by_node["syn_known"]["value"] is True
        assert (
            by_node["syn_known"]["source_path"]
            == "encounters.draft_data.history.values.synthetic_flag_true"
        )
        assert by_node["syn_missing"]["status"] == "missing"
        assert (
            by_node["syn_missing"]["source_path"]
            == "encounters.draft_data.history.values.synthetic_flag_unknown"
        )
        assert by_node["syn_not_assessed"]["status"] == "not_assessed"
        assert (
            by_node["syn_not_assessed"]["source_path"]
            == "encounters.draft_data.history.values.synthetic_flag_not_assessed"
        )
        assert by_node["syn_conflict"]["status"] == "conflict"
        assert (
            by_node["syn_conflict"]["source_path"]
            == "encounters.draft_data.synthetic_conflict"
        )

        variables_dump = json.dumps(variables)
        assert UNRELATED_HISTORY_SENTINEL not in variables_dump
        assert UNRELATED_MED_SENTINEL not in variables_dump

        dumped = json.dumps(body)
        for sentinel in (
            SENTINEL_FIRST,
            SENTINEL_LAST,
            SENTINEL_PID,
            SENTINEL_PHONE,
            SENTINEL_NOTE_SLICE2,
        ):
            assert sentinel not in dumped


def test_mapping_rejects_notes_regardless_of_prompt_slice2():
    """Mapping rejection ignores prompt wording (RED, 422 chosen).

    Rejection rule (backend contract): POST /runs validates every
    patient_mapping.allowed_source_paths at run start. Any path
    containing "notes" (case-insensitive, e.g.
    "encounters.draft_data.notes" or "notes") or any PII path outside
    analysis-visible facts (e.g. "encounters.phone") is INVALID_CONTENT
    -> 422, regardless of accompanying prompt text such as "also read
    notes". No partial run row/projection is created: an unknown run id
    stays 404, and a correct retry after fixing the bundle succeeds.

    RED: the current run start accepts any pins JSON, so the bad POST
    returns 202 instead of 422.
    """
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "snapdocS2B")
        _login(physician, "snapdocS2B", "secret", "physician")
        _patient, encounter = _create_sentinel_patient(
            physician, SLICE2_PID_REJECTION, "s40-s2-rej-patient"
        )
        encounter_id = encounter["id"]
        saved = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": _mapping_draft_with_states()},
            headers=_mutation_headers(physician, revision=encounter["revision"]),
        )
        assert saved.status_code == 200
        noted = physician.post(
            f"/api/v1/encounters/{encounter_id}/notes",
            json={"page": "history", "text": SENTINEL_NOTE_SLICE2},
            headers=_mutation_headers(physician, key="s40-s2-rej-note-1"),
        )
        assert noted.status_code == 201
        revision = _current_revision(physician, encounter_id)

        bad_notes = [
            {
                "node_id": "syn_bad_notes",
                "allowed_source_paths": ["encounters.draft_data.notes"],
                "typed_transform": "string",
                "time_window": "current",
                "usage": "observation",
                "missing_policy": "missing",
            }
        ]
        _insert_mapping_bundle(
            bad_notes,
            prompt=(
                "Estimate every CPT in percentages. Also read notes for "
                "extra context. Do not write a plan."
            ),
        )
        denied_notes = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s40-s2-rej-run-notes", revision=revision
            ),
        )
        assert denied_notes.status_code == 422

        bad_pii = [
            {
                "node_id": "syn_bad_pii",
                "allowed_source_paths": ["encounters.phone"],
                "typed_transform": "string",
                "time_window": "current",
                "usage": "observation",
                "missing_policy": "missing",
            }
        ]
        _insert_mapping_bundle(
            bad_pii,
            prompt=(
                "Estimate every CPT in percentages. Also read notes for "
                "extra context. Do not write a plan."
            ),
        )
        denied_pii = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s40-s2-rej-run-pii", revision=revision
            ),
        )
        assert denied_pii.status_code == 422

        unknown_id = "00000000-0000-0000-0000-000000000000"
        assert physician.get(f"/api/v1/runs/{unknown_id}").status_code == 404

        _insert_mapping_bundle(_valid_slice2_mappings())
        retried = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s40-s2-rej-run-fixed", revision=revision
            ),
        )
        assert retried.status_code == 202
        run_id = retried.json()["run_id"]
        assert physician.get(f"/api/v1/runs/{run_id}").status_code == 200


# ---------------------------------------------------------------------------
# S40 slice 3 (RED): fingerprint stability vs analytical change + immutable
# old snapshots (T1).
#
# Contract under test (tasks.md S40.3; plan.md 4.2/8.1 and p.363):
# - note-only edits (page notes live in encounter_notes, never draft_data;
#   phone is optional non-analytical text) leave the analysis fingerprint
#   unchanged. A run started after such edits at the same encounter
#   revision freezes an identical fingerprint/snapshot_hash.
# - analytical edits (draft_data analytical facts) change the fingerprint
#   and snapshot_hash. Old runs are marked stale: GET /runs exposes a
#   top-level ``stale`` bool (True for superseded runs, False for the
#   current one), which S49 consumes as signing (in)eligibility.
# - old snapshots stay immutable and readable (200) after demographics or
#   history changes; frozen facts/projections never gain the new values,
#   and note/PII sentinels never appear in any run dump.
#
# RED: GET /runs exposes no ``stale`` flag, so the staleness assertions
# fail (KeyError) while the stability/immutability assertions hold.
# ---------------------------------------------------------------------------

SLICE3_PID_A = "0799000061"
SLICE3_PID_B = "0799000062"
SENTINEL_NOTE_SLICE3 = "SENTINEL-NOTE-TEXT-s40-slice3-only"
SENTINEL_PHONE_SLICE3_NEW = "SENTINEL-PHONE-0003-NEW"


def _flipped_slice3_draft():
    """Full clinical draft with one analytical fact flipped (True->False)."""
    draft = _clinical_draft()
    values = {
        **draft["history"]["values"],
        "synthetic_flag_true": {"status": "known", "value": False},
    }
    return {**draft, "history": {**draft["history"], "values": values}}


def _start_run(physician, encounter_id, revision, key):
    started = physician.post(
        f"/api/v1/encounters/{encounter_id}/runs",
        json={"encounter_revision": revision},
        headers=_mutation_headers(physician, key=key, revision=revision),
    )
    assert started.status_code == 202
    return started.json()["run_id"]


def _get_run(physician, run_id):
    fetched = physician.get(f"/api/v1/runs/{run_id}")
    assert fetched.status_code == 200
    return fetched.json()


def test_fingerprint_note_vs_analytical_slice3():
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "snapdocS3A")
        _login(physician, "snapdocS3A", "secret", "physician")
        patient, encounter = _create_sentinel_patient(
            physician, SLICE3_PID_A, "s40-s3-fp-patient"
        )
        encounter_id = encounter["id"]
        saved = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": _clinical_draft()},
            headers=_mutation_headers(physician, revision=encounter["revision"]),
        )
        assert saved.status_code == 200

        _insert_synthetic_bundle()
        revision = _current_revision(physician, encounter_id)
        run1 = _start_run(physician, encounter_id, revision, "s40-s3-fp-run-1")
        body1 = _get_run(physician, run1)
        fingerprint1 = body1["fingerprint"]
        snapshot_hash1 = body1["snapshot_hash"]
        assert fingerprint1 and snapshot_hash1

        noted = physician.post(
            f"/api/v1/encounters/{encounter_id}/notes",
            json={"page": "history", "text": SENTINEL_NOTE_SLICE3},
            headers=_mutation_headers(physician, key="s40-s3-fp-note-1"),
        )
        assert noted.status_code == 201
        assert _current_revision(physician, encounter_id) == revision

        phone_patched = physician.patch(
            f"/api/v1/patients/{patient['id']}",
            json={"phone": SENTINEL_PHONE_SLICE3_NEW},
            headers=_mutation_headers(physician, revision=patient["revision"]),
        )
        assert phone_patched.status_code == 200
        assert phone_patched.json()["patient"]["phone"] == SENTINEL_PHONE_SLICE3_NEW

        reread1 = _get_run(physician, run1)
        assert reread1["snapshot_hash"] == snapshot_hash1
        assert reread1["fingerprint"] == fingerprint1
        assert reread1["projections"] == body1["projections"]

        run2 = _start_run(physician, encounter_id, revision, "s40-s3-fp-run-2")
        body2 = _get_run(physician, run2)
        assert body2["fingerprint"] == fingerprint1
        assert body2["snapshot_hash"] == snapshot_hash1

        edited = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": _flipped_slice3_draft()},
            headers=_mutation_headers(physician, revision=revision),
        )
        assert edited.status_code == 200
        revision3 = int(edited.json()["encounter"]["revision"])
        assert revision3 == revision + 1

        run3 = _start_run(physician, encounter_id, revision3, "s40-s3-fp-run-3")
        body3 = _get_run(physician, run3)
        assert body3["fingerprint"] != fingerprint1
        assert body3["snapshot_hash"] != snapshot_hash1

        for dump in (
            json.dumps(reread1),
            json.dumps(body2),
            json.dumps(body3),
        ):
            for sentinel in (
                SENTINEL_FIRST,
                SENTINEL_LAST,
                SLICE3_PID_A,
                SENTINEL_PHONE,
                SENTINEL_PHONE_SLICE3_NEW,
                SENTINEL_NOTE_SLICE3,
            ):
                assert sentinel not in dump

        # RED: superseded runs read stale; the current run does not.
        assert _get_run(physician, run1)["stale"] is True
        assert _get_run(physician, run2)["stale"] is True
        assert _get_run(physician, run3)["stale"] is False


def test_snapshot_immutable_after_changes_slice3():
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "snapdocS3B")
        _login(physician, "snapdocS3B", "secret", "physician")
        patient, encounter = _create_sentinel_patient(
            physician, SLICE3_PID_B, "s40-s3-imm-patient"
        )
        encounter_id = encounter["id"]
        saved = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": _clinical_draft()},
            headers=_mutation_headers(physician, revision=encounter["revision"]),
        )
        assert saved.status_code == 200

        _insert_synthetic_bundle()
        revision = _current_revision(physician, encounter_id)
        run1 = _start_run(physician, encounter_id, revision, "s40-s3-imm-run-1")
        body1 = _get_run(physician, run1)

        noted = physician.post(
            f"/api/v1/encounters/{encounter_id}/notes",
            json={"page": "history", "text": SENTINEL_NOTE_SLICE3},
            headers=_mutation_headers(physician, key="s40-s3-imm-note-1"),
        )
        assert noted.status_code == 201

        phone_patched = physician.patch(
            f"/api/v1/patients/{patient['id']}",
            json={"phone": SENTINEL_PHONE_SLICE3_NEW},
            headers=_mutation_headers(physician, revision=patient["revision"]),
        )
        assert phone_patched.status_code == 200

        edited = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": _flipped_slice3_draft()},
            headers=_mutation_headers(physician, revision=revision),
        )
        assert edited.status_code == 200

        reread = _get_run(physician, run1)
        assert reread["snapshot_hash"] == body1["snapshot_hash"]
        assert reread["fingerprint"] == body1["fingerprint"]
        assert reread["projections"] == body1["projections"]
        frozen_facts = reread["projections"][0]["projection"]["facts"]
        assert frozen_facts["history"]["values"]["synthetic_flag_true"]["value"] is True
        dumped = json.dumps(reread)
        for sentinel in (
            SENTINEL_FIRST,
            SENTINEL_LAST,
            SLICE3_PID_B,
            SENTINEL_PHONE,
            SENTINEL_PHONE_SLICE3_NEW,
            SENTINEL_NOTE_SLICE3,
        ):
            assert sentinel not in dumped

        # RED: frozen content stays readable but is no longer current.
        assert reread["stale"] is True


# ---------------------------------------------------------------------------
# S40 slice 4 (RED): applicability gates + forbid cross-question inputs (T1).
#
# Pins carrier (test-only, never a production default): synthetic bundle pins
# JSON embeds per-question ``applicability`` for the synthetic question only.
# Real registry pins (S24) lack this until S39 bundles. ONE gate shape:
#
#   pins.questions[0].applicability = {
#       "expression": "encounters.draft_data.history.values."
#                     "synthetic_flag_true == true",
#       "required_fields": [
#           "encounters.draft_data.history.values.synthetic_flag_true"
#       ],
#       "unknown_policy": "needs_clarification",
#   }
#
# Expression allowlist (backend contract): a single ``== true`` / ``== false``
# comparison whose left side equals one entry of required_fields; left side
# and every required_field must be an allowlisted patient-fact path (same
# allowlist as patient_mappings: encounters.draft_data.* analytical facts,
# patients.clinical_status, encounter kind; never notes/PII/questions.*).
# unknown_policy is "needs_clarification" in this slice.
#
# Evaluation against SAVED (frozen) facts (plan.md 7.1: true executes; false
# -> not_applicable with reason; unknown required -> needs_clarification
# stopping later; no implicit chaining of posteriors):
# - any required_field resolving to unknown/missing/not_assessed/conflict
#   (per snapshots._resolve_status_value mapping) -> needs_clarification
#   with reason naming the unknown field;
# - else expression true -> ready with reason stating the evaluated value;
# - else expression false -> not_applicable with explicit reason.
# Unknown is never false. Reasons are non-empty strings.
#
# Status vocabulary: {ready, not_applicable, needs_clarification}.
#
# Persistence (minimal extension of the current GET shape): current GET /runs
# returns top-level ``stale`` bool plus projections[] entries with
# {question_key, projection_hash, projection}. The backend must add to EACH
# projections[] entry:
#   "applicability": one of the three statuses above (str),
#   "applicability_reason": non-empty str.
# Gates are evaluated at run start from frozen facts and persisted per
# run_questions row (returned verbatim by GET /runs).
#
# Cross-question rejection rule (backend contract): ANY string in a
# pins.questions[] entry that references another question's result/posterior
# -- i.e. contains substring "questions." such as
# "questions.other.result" or "questions.synthetic_example.posterior" in
# allowed_source_paths, applicability.expression, applicability
# .required_fields, or any evidence/query mapping -- is INVALID_CONTENT ->
# POST /runs 422, regardless of prompt text attempting to authorize it
# (e.g. "use the other question's posterior"). No partial run row/projection
# is created; a fixed-bundle retry at the same revision succeeds.
#
# RED: current code performs no gate evaluation (projections[] entries carry
# no applicability keys) and validates only patient_mappings paths, so gate
# assertions fail with KeyError and chained-gate bundles are accepted (202).
# ---------------------------------------------------------------------------

SLICE4_BUNDLE_HASH_GATE = "synthetic-bundle-hash-s40-slice4-gate"
SLICE4_NETWORK_HASH_GATE = "synthetic-network-hash-s40-slice4"
SLICE4_BUNDLE_HASH_CROSS = "synthetic-bundle-hash-s40-slice4-cross"

SLICE4_PID_TRUE = "0799000071"
SLICE4_PID_FALSE = "0799000072"
SLICE4_PID_UNKNOWN = "0799000073"
SLICE4_PID_CROSS = "0799000074"

SLICE4_GATE_EXPRESSION = (
    "encounters.draft_data.history.values.synthetic_flag_true == true"
)
SLICE4_GATE_REQUIRED = [
    "encounters.draft_data.history.values.synthetic_flag_true"
]
SLICE4_GATE_POLICY = "needs_clarification"


def _gate_draft(flag_status, flag_value):
    base = _clinical_draft()
    values = {
        **base["history"]["values"],
        "synthetic_flag_true": {"status": flag_status, "value": flag_value},
    }
    return {**base, "history": {**base["history"], "values": values}}


def _insert_slice4_bundle(bundle_hash, question):
    pins = {"questions": [question]}
    with db.transaction() as conn:
        conn.execute(
            text(
                "INSERT INTO model_bundle_pointers "
                "(workflow, revision, bundle_hash, pins) "
                "VALUES ('registration', 1, :hash, CAST(:pins AS jsonb)) "
                "ON CONFLICT (workflow) DO UPDATE SET revision = 1, "
                "bundle_hash = :hash, pins = CAST(:pins AS jsonb)"
            ),
            {"hash": bundle_hash, "pins": json.dumps(pins)},
        )
        conn.execute(
            text(
                "INSERT INTO model_bundle_events "
                "(workflow, revision, bundle_hash, pins, action) "
                "VALUES ('registration', 1, :hash, CAST(:pins AS jsonb), "
                "'activate') ON CONFLICT (workflow, revision) DO NOTHING"
            ),
            {"hash": bundle_hash, "pins": json.dumps(pins)},
        )


def _gate_question():
    return {
        "question_key": SYNTHETIC_QUESTION,
        "version": "synthetic-v1",
        "network_hash": SLICE4_NETWORK_HASH_GATE,
        "applicability": {
            "expression": SLICE4_GATE_EXPRESSION,
            "required_fields": list(SLICE4_GATE_REQUIRED),
            "unknown_policy": SLICE4_GATE_POLICY,
        },
    }


def _start_and_fetch(physician, encounter_id, revision, key):
    started = physician.post(
        f"/api/v1/encounters/{encounter_id}/runs",
        json={"encounter_revision": revision},
        headers=_mutation_headers(physician, key=key, revision=revision),
    )
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    fetched = physician.get(f"/api/v1/runs/{run_id}")
    assert fetched.status_code == 200
    return fetched.json()


def test_gate_ready_applicable_clarification_slice4():
    """Gate true/false/required-unknown -> persisted status + reason (RED).

    Same synthetic gate (see module header) evaluated against three saved
    drafts: known True -> ready; known False -> not_applicable; unknown
    (status unknown, value None) -> needs_clarification. Each GET /runs
    projections[] entry for the synthetic question must carry
    ``applicability`` in {ready, not_applicable, needs_clarification} plus
    non-empty ``applicability_reason`` mentioning the gate field. Top-level
    ``stale`` remains present.

    RED: entries carry no applicability keys, so the status assertions fail.
    """
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "snapdocS4A")
        _login(physician, "snapdocS4A", "secret", "physician")
        _insert_slice4_bundle(SLICE4_BUNDLE_HASH_GATE, _gate_question())

        cases = [
            (SLICE4_PID_TRUE, "known", True, "s40-s4-gate-true", "ready"),
            (SLICE4_PID_FALSE, "known", False, "s40-s4-gate-false", "not_applicable"),
            (
                SLICE4_PID_UNKNOWN,
                "unknown",
                None,
                "s40-s4-gate-unknown",
                "needs_clarification",
            ),
        ]
        for pid, status, value, key, expected in cases:
            _patient, encounter = _create_sentinel_patient(
                physician, pid, f"{key}-patient"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _gate_draft(status, value)},
                headers=_mutation_headers(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            body = _start_and_fetch(physician, encounter_id, revision, f"{key}-run")
            assert body["stale"] is False
            projections = body.get("projections")
            assert isinstance(projections, list) and len(projections) >= 1
            entry = next(
                item
                for item in projections
                if item.get("question_key") == SYNTHETIC_QUESTION
            )
            # RED: keys absent today (KeyError / assertion failure).
            assert entry["applicability"] == expected
            reason = entry["applicability_reason"]
            assert isinstance(reason, str) and reason.strip()
            assert "synthetic_flag_true" in reason


def test_forbid_cross_question_inputs_slice4():
    """Cross-question result inputs are INVALID_CONTENT -> 422 (RED).

    Vectors (same synthetic question; prompt tries to authorize chaining):
    A. patient_mappings.allowed_source_paths = ["questions.other.result"];
    B. valid mappings + applicability.expression referencing
       "questions.synthetic_example.posterior" (implicit posterior chaining,
       forbidden by plan.md 7.1). Both must yield 422 with no partial run;
    a fixed-bundle retry at the same revision yields 202.

    RED: vector A already yields 422 via the path allowlist, but vector B
    is accepted (202) because applicability expressions are unvalidated, so
    the second 422 assertion fails.
    """
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "snapdocS4B")
        _login(physician, "snapdocS4B", "secret", "physician")
        _patient, encounter = _create_sentinel_patient(
            physician, SLICE4_PID_CROSS, "s40-s4-cross-patient"
        )
        encounter_id = encounter["id"]
        saved = physician.patch(
            f"/api/v1/encounters/{encounter_id}",
            json={"draft_data": _gate_draft("known", True)},
            headers=_mutation_headers(physician, revision=encounter["revision"]),
        )
        assert saved.status_code == 200
        revision = _current_revision(physician, encounter_id)

        chained_mapping = [
            {
                "node_id": "syn_chained",
                "allowed_source_paths": ["questions.other.result"],
                "typed_transform": "boolean",
                "time_window": "current",
                "usage": "observation",
                "missing_policy": "missing",
            }
        ]
        _insert_slice4_bundle(
            SLICE4_BUNDLE_HASH_CROSS,
            {
                "question_key": SYNTHETIC_QUESTION,
                "version": "synthetic-v1",
                "network_hash": SLICE4_NETWORK_HASH_GATE,
                "patient_mappings": chained_mapping,
                "prompt": "Estimate every CPT. Use questions.other.result.",
            },
        )
        denied_mapping = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s40-s4-cross-run-mapping", revision=revision
            ),
        )
        assert denied_mapping.status_code == 422

        chained_gate = _gate_question()
        chained_gate["patient_mappings"] = _valid_slice2_mappings()
        chained_gate["applicability"] = {
            "expression": "questions.synthetic_example.posterior == true",
            "required_fields": ["questions.synthetic_example.posterior"],
            "unknown_policy": "needs_clarification",
        }
        chained_gate["prompt"] = (
            "Estimate every CPT. Use the other question's posterior."
        )
        _insert_slice4_bundle(SLICE4_BUNDLE_HASH_CROSS, chained_gate)
        denied_gate = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s40-s4-cross-run-gate", revision=revision
            ),
        )
        # RED: currently 202 (unchained gate accepted).
        assert denied_gate.status_code == 422

        unknown_id = "00000000-0000-0000-0000-000000000000"
        assert physician.get(f"/api/v1/runs/{unknown_id}").status_code == 404

        _insert_slice4_bundle(SLICE4_BUNDLE_HASH_GATE, _gate_question())
        retried = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s40-s4-cross-run-fixed", revision=revision
            ),
        )
        assert retried.status_code == 202
        run_id = retried.json()["run_id"]
        assert physician.get(f"/api/v1/runs/{run_id}").status_code == 200
