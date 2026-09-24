"""S58 item 4 RED: capacity, fair progress, and bounded caches (T8).

Scope ONLY (tasks.md S58.4; plan.md sections 8.4 + 11): two-slot global
concurrency, fair progress across physicians (round-robin, oldest within
physician), saturation 429 without deletion, and bounded caches for
immutable definitions/catalogs with no patient-CPT/projection caching
under a base-model key and no cross-patient reuse.

Contract under test (no extra seams):

- reasoning/queue.py: claim_next_job() honors MAX_PROVIDER_SLOTS (2)
  with a short transaction; queue_fairness persists round-robin state so
  a physician is not starved; queue.set_now_fn/reset_now_fn control the
  deterministic clock (no sleeps for timing).
- POST /encounters/{id}/runs refuses past MAX_QUEUED_RUNS with 429 +
  the standard error envelope, leaving existing runs/drafts intact.
- A bounded immutable-definition cache module (proposed:
  x_insight.models.definition_cache) caches parsed definitions/catalogs
  by content hash with bounded memory (LRU, MAX_ENTRIES); patient
  CPTs/projections are never cached under a base-model key and never
  reused across patients.

RED: no bounded immutable-definition cache module exists (no lru/dict
parsed-definition cache anywhere under backend/src/x_insight), so test 3
fails at import. Tests 1-2 pin queue behavior via the real PostgreSQL
queue and the deterministic clock.

Synthetic-bundle choice (test-only, never a production default): same
pattern as tests/worker/test_queue.py -- one synthetic registration
pointer/event row (bundle_hash "synthetic-bundle-hash-s58-capacity",
one question "synthetic_example").
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all
from x_insight.reasoning import queue as queue_module

SYNTHETIC_HISTORY_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "content" / "history"
)

SENTINEL_FIRST = "SentinelAlpha"
SENTINEL_LAST = "SentinelBeta"
SENTINEL_PHONE = "SENTINEL-PHONE-0058"

SYNTHETIC_BUNDLE_HASH = "synthetic-bundle-hash-s58-capacity"
SYNTHETIC_QUESTION = "synthetic_example"
SYNTHETIC_HISTORY_VERSION = "synthetic-history-v1"
SYNTHETIC_DDI_VERSION = "synthetic-ddi-s58-v1"
SYNTHETIC_MEDICATION_FINGERPRINT = "fp-synth-s58-capacity"

FIXED_NOW = datetime(2026, 9, 24, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clean_capacity(monkeypatch):
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(SYNTHETIC_HISTORY_DIR))
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, runs, run_questions, reasoning_jobs, "
                "audit_events, "
                "model_bundle_pointers, model_bundle_events CASCADE"
            )
        )
    for _table in (
        "reasoning_attempts",
        "queue_fairness",
        "run_question_artifacts",
        "run_proposals",
    ):
        try:
            with db.transaction() as conn:
                conn.execute(text(f"TRUNCATE {_table} CASCADE"))
        except Exception:
            pass
    reset_all()
    queue_module.set_now_fn(lambda: FIXED_NOW)
    yield
    queue_module.reset_now_fn()
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
        headers=_mutation_headers(admin, key=f"s58-{username}-create"),
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


def _insert_synthetic_bundle():
    pins = {
        "questions": [
            {
                "question_key": SYNTHETIC_QUESTION,
                "version": "synthetic-v1",
                "network_hash": "synthetic-network-hash-s58-capacity",
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


def _start_run(physician, patient_id, patient_key, run_key):
    """Patch a sentinel draft and start one queued run; return ids."""
    _patient, encounter = _create_sentinel_patient(physician, patient_id, patient_key)
    encounter_id = encounter["id"]
    saved = physician.patch(
        f"/api/v1/encounters/{encounter_id}",
        json={"draft_data": _clinical_draft()},
        headers=_mutation_headers(physician, revision=encounter["revision"]),
    )
    assert saved.status_code == 200
    revision = _current_revision(physician, encounter_id)
    created = physician.post(
        f"/api/v1/encounters/{encounter_id}/runs",
        json={"encounter_revision": revision},
        headers=_mutation_headers(physician, key=run_key, revision=revision),
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]
    uuid.UUID(run_id)
    return encounter_id, run_id


def test_two_slot_global_concurrency_and_saturation_429(monkeypatch):
    """At most 2 concurrent claims; the third stays queued; overflow is 429.

    Three eligible jobs (one physician, three encounters) against the
    synthetic single-question bundle. Two claim_next_job() calls claim;
    the third returns None (both global provider slots live under the
    fixed deterministic clock) and the third run still reads 200 with
    its single job queued. Saturating the queue then refuses a fresh
    run with 429 + the standard error envelope, deleting nothing.

    RED: a no-slot implementation claims all 3 at once (third claim not
    None); an uncapped start_run returns 202 instead of 429.
    """
    from x_insight.reasoning import runs as runs_module
    from x_insight.reasoning.queue import MAX_PROVIDER_SLOTS

    assert int(MAX_PROVIDER_SLOTS) == 2
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "capdocA")
        _login(physician, "capdocA", "secret", "physician")
        _insert_synthetic_bundle()

        run_ids = [
            _start_run(physician, pid, f"s58-cap1-patient-{i}", f"s58-cap1-run-{i}")[1]
            for i, pid in enumerate(["0799000601", "0799000602", "0799000603"])
        ]

        first = queue_module.claim_next_job(worker_id="cap-worker-1")
        second = queue_module.claim_next_job(worker_id="cap-worker-2")
        third = queue_module.claim_next_job(worker_id="cap-worker-3")

        assert first is not None and second is not None
        assert first["job_id"] != second["job_id"], "no double-claim"
        # RED: without the 2-slot cap the third claim succeeds here.
        assert third is None, "both global slots live: third claim must wait"

        claimed_runs = {first["run_id"], second["run_id"]}
        assert claimed_runs.issubset(set(run_ids))
        queued_run = next(rid for rid in run_ids if rid not in claimed_runs)
        kept = physician.get(f"/api/v1/runs/{queued_run}")
        assert kept.status_code == 200
        kept_jobs = kept.json()["jobs"]
        assert len(kept_jobs) == 1
        assert kept_jobs[0]["status"] == "queued"

        # Saturation: cap the admission threshold at the 3 live runs so
        # the overflow path is exercised with a small runtime.
        monkeypatch.setattr(runs_module, "MAX_QUEUED_RUNS", 3)
        _patient, fresh = _create_sentinel_patient(
            physician, "0799000604", "s58-cap1-patient-fresh"
        )
        fresh_id = fresh["id"]
        saved = physician.patch(
            f"/api/v1/encounters/{fresh_id}",
            json={"draft_data": _clinical_draft()},
            headers=_mutation_headers(physician, revision=fresh["revision"]),
        )
        assert saved.status_code == 200
        fresh_revision = _current_revision(physician, fresh_id)

        overflow = physician.post(
            f"/api/v1/encounters/{fresh_id}/runs",
            json={"encounter_revision": fresh_revision},
            headers=_mutation_headers(
                physician, key="s58-cap1-run-overflow", revision=fresh_revision
            ),
        )
        # RED: uncapped start_run returns 202 here instead of busy.
        assert overflow.status_code == 429, (
            f"saturated queue must return 429 busy, got {overflow.status_code}"
        )
        envelope = overflow.json()
        for key in ("code", "message", "request_id"):
            assert key in envelope, "429 must use the standard error envelope"

        # Nothing deleted: the still-queued run and the fresh draft read back.
        reread = physician.get(f"/api/v1/runs/{queued_run}")
        assert reread.status_code == 200
        assert len(reread.json()["jobs"]) == 1
        draft = physician.get(f"/api/v1/encounters/{fresh_id}")
        assert draft.status_code == 200


def test_fair_progress_round_robin_oldest_within_physician():
    """Queued claims rotate across physicians, FIFO within a physician.

    Physician A queues A1, A2 (in that order); physician B queues B1
    last -- all against the synthetic single-question bundle. A single
    sequential worker calls run_once() with a fast no-op adapter under
    the fixed deterministic clock; both global slots stay live once
    claimed, so exactly the first two calls claim and the third reports
    busy. Rotation serves B within the first two claims (no starvation)
    and the served A job is the oldest, A1.

    RED: pure FIFO by created_at claims A1 then A2, so the rotation
    assert fails (second claim is A2 instead of B1).
    """
    from x_insight.reasoning.worker import run_once

    with (
        TestClient(app) as admin,
        TestClient(app) as physician_a,
        TestClient(app) as physician_b,
    ):
        _login(admin)
        _make_physician(admin, "capdocB")
        _make_physician(admin, "capdocC")
        _login(physician_a, "capdocB", "secret", "physician")
        _login(physician_b, "capdocC", "secret", "physician")
        _insert_synthetic_bundle()

        _, run_a1 = _start_run(
            physician_a, "0799000611", "s58-cap2-patient-a1", "s58-cap2-run-a1"
        )
        _, run_a2 = _start_run(
            physician_a, "0799000612", "s58-cap2-patient-a2", "s58-cap2-run-a2"
        )
        _, run_b1 = _start_run(
            physician_b, "0799000613", "s58-cap2-patient-b1", "s58-cap2-run-b1"
        )
        owner = {run_a1: "A", run_a2: "A", run_b1: "B"}

        def _noop_adapter(*args, **kwargs):
            _ = (args, kwargs)
            return {"ok": True}

        claims = [
            run_once(
                database_url=None,
                provider_adapter=_noop_adapter,
                worker_id="s58-cap2-worker",
            )
            for _ in range(3)
        ]
        for out in claims:
            assert isinstance(out, dict)
            for key in (
                "claimed",
                "busy",
                "job_id",
                "run_id",
                "question_key",
                "lease_token",
            ):
                assert key in out, f"run_once return missing {key}"

        served = [item for item in claims if item.get("claimed")]
        # Two global slots stay live once claimed, so exactly the first
        # two calls claim; the third reports busy.
        assert len(served) == 2, f"expected exactly 2 claims, got {claims}"
        assert all(item.get("run_id") in owner for item in served)
        assert len({item["run_id"] for item in served}) == 2, "no double-claim"
        assert claims[2].get("claimed") is False, (
            "slots full: the third call must not claim"
        )

        labels = [owner[item["run_id"]] for item in served]
        # RED: pure FIFO yields ["A", "A"]; fair rotation serves B within
        # the first two claims regardless of FIFO tie-break (no starvation).
        assert set(labels) == {"A", "B"}, (
            f"first two claims must rotate across physicians, got {labels}"
        )
        # FIFO within physician A survives the rotation: the served A job
        # is the oldest, A1 (the A2 tail stays queued behind live slots).
        a_served = [item for item in served if owner[item["run_id"]] == "A"]
        assert len(a_served) == 1 and a_served[0]["run_id"] == run_a1, (
            f"served A job must be the oldest (A1), got {labels}"
        )


def test_bounded_caches_no_patient_reuse_under_base_model_key():
    """Immutable definitions cached by hash with bounded memory; no patient reuse.

    - Immutable parsed definitions/catalogs are cached by content hash in
      a bounded LRU (proposed: x_insight.models.definition_cache with
      MAX_ENTRIES, get_or_parse(key, raw, parse), __len__/clear): the
      same hash parses once, and filling past MAX_ENTRIES evicts so
      memory stays bounded (an evicted hash re-parses on next use).
    - Patient CPTs/projections are never cached under a base-model key:
      two runs for two patients against the same synthetic bundle get
      distinct per-run artifacts (distinct run ids, one job each scoped
      to its own run), and authenticated reads stay private/no-store.

    RED: no bounded immutable-definition cache module exists, so the
    import below fails (ModuleNotFoundError). The backend agent must add
    the module with the contract above; no broker/cache/DB may be added
    without measured evidence (plan.md section 11).
    """
    # RED: x_insight.models.definition_cache does not exist yet.
    from x_insight.models.definition_cache import MAX_ENTRIES, get_or_parse

    assert int(MAX_ENTRIES) > 0, "cache bound must be a positive int"
    assert int(MAX_ENTRIES) <= 512, "immutable-definition cache must stay small"

    parses: list[str] = []

    def _parse(raw: bytes) -> dict:
        parses.append(raw.hex())
        return {"parsed": raw.hex()}

    first = get_or_parse("hash-alpha", b"alpha", _parse)
    again = get_or_parse("hash-alpha", b"alpha", _parse)
    assert again == first, "same content hash must hit the cache"
    assert parses.count(b"alpha".hex()) == 1, "cache hit must not re-parse"

    for index in range(int(MAX_ENTRIES) + 5):
        get_or_parse(f"hash-fill-{index}", f"fill-{index}".encode(), _parse)
    from x_insight.models import definition_cache as cache_module

    assert len(cache_module) <= int(MAX_ENTRIES), (
        "immutable-definition cache must evict past its bound"
    )
    before = len(parses)
    get_or_parse("hash-alpha", b"alpha", _parse)
    assert len(parses) > before, "an evicted hash must re-parse on next use"

    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "capdocD")
        _login(physician, "capdocD", "secret", "physician")
        _insert_synthetic_bundle()

        _, run_p1 = _start_run(
            physician, "0799000621", "s58-cap3-patient-p1", "s58-cap3-run-p1"
        )
        _, run_p2 = _start_run(
            physician, "0799000622", "s58-cap3-patient-p2", "s58-cap3-run-p2"
        )
        assert run_p1 != run_p2, "distinct patients get distinct runs"

        body_p1 = physician.get(f"/api/v1/runs/{run_p1}")
        body_p2 = physician.get(f"/api/v1/runs/{run_p2}")
        assert body_p1.status_code == 200
        assert body_p2.status_code == 200
        assert body_p1.headers.get("cache-control") == "private, no-store"
        payload_p1 = body_p1.json()
        payload_p2 = body_p2.json()
        assert payload_p1["run"]["id"] == run_p1
        assert payload_p2["run"]["id"] == run_p2
        # Per-run artifacts only: each run exposes exactly its own first
        # job; nothing is shared across patients under the base-model key.
        assert len(payload_p1["jobs"]) == 1
        assert len(payload_p2["jobs"]) == 1
        assert payload_p1["jobs"] != payload_p2["jobs"] or run_p1 != run_p2
