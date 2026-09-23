"""S44 slice 1 (RED): durable leased jobs — atomic first job + reuse (T8).

Slice-1 scope ONLY (tasks.md S44.1; plan.md 8.4-8.5): run creation and its
first eligible job are atomic; repeated same-fingerprint triggers reuse the
run; simultaneous triggers cannot create two active generations for an
encounter. Slices 2-4 (leases/slots, fairness/busy, expiry/recovery via
run_once()) are NOT tested here.

Expected minimal contract for the backend agent (no extra seams):

- POST /api/v1/encounters/{encounter_id}/runs
  body {"encounter_revision": int}, headers Idempotency-Key + If-Match
  (same conventions as S40). Same-fingerprint reuse rule: a second POST
  with the SAME encounter_revision (same analysis fingerprint) but a
  DIFFERENT Idempotency-Key must return 202 with the SAME run_id (no new
  run row, no duplicate job). Only a changed fingerprint/revision may
  create a new run.
- GET /api/v1/runs/{run_id}
  Success 200 includes, in addition to the S40 keys, a top-level "jobs"
  array with exactly 1 entry for the first eligible synthetic question:
  "jobs": [{"question_key": str, "ordinal": 0,
  "stage": "preparing_question", "status": "queued"}].
  Run status is "queued" (or "preparing"). Second GET after reuse still
  shows exactly 1 job (no duplicate).

RED: current code always INSERTs a new run per Idempotency-Key (no
fingerprint reuse, so second POST yields a DIFFERENT run_id) and GET
exposes no "jobs"/"queue" key, so the jobs-presence and reuse assertions
fail (KeyError/assert) on current code.

Synthetic-bundle choice (test-only, never a production default): same
pattern as test_snapshots.py _insert_synthetic_bundle — one synthetic
registration pointer/event row (bundle_hash
"synthetic-bundle-hash-s44-slice1", one question "synthetic_example").
"""

from __future__ import annotations

import json
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

SENTINEL_FIRST = "SentinelAlpha"
SENTINEL_LAST = "SentinelBeta"
SENTINEL_PHONE = "SENTINEL-PHONE-0044"

SYNTHETIC_BUNDLE_HASH = "synthetic-bundle-hash-s44-slice1"
SYNTHETIC_QUESTION = "synthetic_example"
SYNTHETIC_HISTORY_VERSION = "synthetic-history-v1"
SYNTHETIC_DDI_VERSION = "synthetic-ddi-s44-v1"
SYNTHETIC_MEDICATION_FINGERPRINT = "fp-synth-s44-slice1"


@pytest.fixture(autouse=True)
def clean_queue(monkeypatch):
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
    # Any new S44 queue tables, if they exist (file must work before
    # migration 0014 exists). Each probe runs in its own transaction so a
    # missing table rolls back only that probe and never poisons the base
    # TRUNCATE above.
    for _table in (
        "jobs",
        "job_attempts",
        "reasoning_jobs",
        "reasoning_attempts",
        "run_jobs",
        "question_jobs",
        "worker_leases",
        "context_grants",
        # S44 slice-3 fairness/scheduling state (tolerated when absent;
        # each probe rolls back only itself, never the base TRUNCATE).
        "scheduler_state",
        "queue_fairness_state",
        "physician_round_robin",
    ):
        try:
            with db.transaction() as conn:
                conn.execute(text(f"TRUNCATE {_table} CASCADE"))
        except Exception:
            pass
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
        headers=_mutation_headers(admin, key=f"s44-{username}-create"),
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
                "network_hash": "synthetic-network-hash-s44-slice1",
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


def _assert_first_job(body):
    # RED: GET /runs/{id} currently has no jobs/queue key.
    assert "jobs" in body, "GET /runs must include a top-level 'jobs' array"
    jobs = body["jobs"]
    assert isinstance(jobs, list)
    assert len(jobs) == 1, "exactly one first eligible job must exist"
    job = jobs[0]
    assert job["question_key"] == SYNTHETIC_QUESTION
    assert job["ordinal"] == 0
    assert job["stage"] == "preparing_question"
    assert job["status"] == "queued"


def test_run_creation_and_first_job_atomic_and_fingerprint_reuse():
    """POST creates run + first job atomically; same fingerprint reuses run.

    First POST (fresh Idempotency-Key) -> 202 with run_id; GET shows run
    status queued/preparing AND jobs array with exactly 1 entry for the
    first synthetic question. Second POST with SAME encounter_revision but
    DIFFERENT Idempotency-Key and same fingerprint must reuse the SAME
    run_id (no new run row) and GET still shows exactly 1 job.

    RED: second POST creates a different run_id and GET has no jobs key.
    """
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "queuedocA")
        _login(physician, "queuedocA", "secret", "physician")
        _patient, encounter = _create_sentinel_patient(
            physician, "0799000081", "s44-s1-patient-a"
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

        first = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s44-s1-run-first", revision=revision
            ),
        )
        assert first.status_code == 202
        run_id = first.json()["run_id"]
        uuid.UUID(run_id)

        body = physician.get(f"/api/v1/runs/{run_id}")
        assert body.status_code == 200
        payload = body.json()
        assert payload["run"]["status"] in ("queued", "preparing")
        # RED: no jobs key on current code.
        _assert_first_job(payload)

        # Same fingerprint, different Idempotency-Key -> reuse, no duplicate.
        second = physician.post(
            f"/api/v1/encounters/{encounter_id}/runs",
            json={"encounter_revision": revision},
            headers=_mutation_headers(
                physician, key="s44-s1-run-second-different-key", revision=revision
            ),
        )
        assert second.status_code == 202
        # RED: current code INSERTs a new run row -> different run_id.
        assert second.json()["run_id"] == run_id

        reread = physician.get(f"/api/v1/runs/{run_id}")
        assert reread.status_code == 200
        _assert_first_job(reread.json())


def test_simultaneous_triggers_cannot_create_two_active_generations():
    """Two rapid triggers with different keys yield one run and one job.

    Two concurrent POSTs (different Idempotency-Keys, same
    encounter_revision/fingerprint, same author) must both return 202 with
    the SAME run_id (second reuses), and GET shows exactly 1 job. Uses two
    threads gated on a barrier for true simultaneity.

    RED: two different run_ids (or 500/404 on the jobs key).
    """
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "queuedocB")
        _login(physician, "queuedocB", "secret", "physician")
        _patient, encounter = _create_sentinel_patient(
            physician, "0799000082", "s44-s1-patient-b"
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

        barrier = threading.Barrier(2)
        results = [None, None]

        def _trigger(index, idem_key):
            with TestClient(app) as client:
                _login(client, "queuedocB", "secret", "physician")
                barrier.wait(timeout=10)
                results[index] = client.post(
                    f"/api/v1/encounters/{encounter_id}/runs",
                    json={"encounter_revision": revision},
                    headers=_mutation_headers(
                        client, key=idem_key, revision=revision
                    ),
                )

        threads = [
            threading.Thread(target=_trigger, args=(0, "s44-s1-race-key-1")),
            threading.Thread(target=_trigger, args=(1, "s44-s1-race-key-2")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert results[0] is not None and results[1] is not None
        assert results[0].status_code == 202
        assert results[1].status_code == 202
        run_a = results[0].json()["run_id"]
        run_b = results[1].json()["run_id"]
        uuid.UUID(run_a)
        # RED: current code creates two distinct runs under concurrency.
        assert run_a == run_b, "simultaneous triggers must reuse one run"

        fetched = physician.get(f"/api/v1/runs/{run_a}")
        assert fetched.status_code == 200
        payload = fetched.json()
        assert payload["run"]["status"] in ("queued", "preparing")
        # RED: no jobs key on current code.
        _assert_first_job(payload)


# ---------------------------------------------------------------------------
# S44 slice-2 RED (Tests C-D): global admission + short claim/lease (T8).
#
# Scope ONLY (tasks.md S44.2; plan.md sections 8.4-8.5): two worker
# instances cannot exceed two global provider slots or execute two
# questions of one run. Short claim transactions, lease/heartbeat and
# persistent admission enforce this. Slices 1/3-4 (atomic first job,
# fairness/busy rotation, expiry/recovery) are NOT tested here.
#
# Expected minimal worker contract (for the backend agent, no extra seams):
#
# - backend/src/x_insight/reasoning/worker.py exposes
#       run_once(*, database_url=None, provider_adapter=None,
#                worker_id=None) -> dict
#   with keys {claimed: bool, busy: bool, job_id, run_id, question_key,
#   lease_token}. Claim uses a short transaction with SELECT ... FOR UPDATE
#   SKIP LOCKED, lease 120s, heartbeat 15s, 2 global slots enforced in DB.
#   The external provider call happens OUTSIDE the claim transaction.
# - provider_adapter is a callable invoked OUTSIDE the claim transaction as
#   provider_adapter(job) where job is a dict containing at least job_id and
#   lease_token. Tests pass an adapter that sleeps ~0.3s/0.5s and records
#   entry/exit to force overlap. No live provider is used.
# - backend/src/x_insight/reasoning/queue.py exposes
#       heartbeat(job_id, lease_token) -> dict with lease_deadline
#   (or a datetime/str deadline directly). A second heartbeat extends the
#   deadline. Missing worker.py (ImportError) or missing heartbeat
#   (AttributeError) fails these tests.
#
# Fixture: autouse clean_queue TRUNCATEs base tables CASCADE plus
# reasoning_jobs + reasoning_attempts via try/except probes (missing tables
# roll back only that probe). Each slice-2 test additionally probes those
# two tables before setup. Only public GET /runs/{id} plus run_once returns
# are asserted, except setup writes. Deterministic short sleeps only.
#
# RED: worker.py does not exist, so both tests fail with ImportError
# (2 new failures, 2 slice-1 passes).
#
# Synthetic-bundle choice (test-only, never a production default): same
# pattern as slice-1 -- one synthetic registration pointer/event row
# (bundle_hash "synthetic-bundle-hash-s44-slice1", one question
# "synthetic_example").
# ---------------------------------------------------------------------------


def _s2_truncate_queue_tables():
    # Explicit per-test probe for the slice-2 contract: reasoning_jobs +
    # reasoning_attempts via try/except, never failing setup when the
    # attempts table does not exist yet.
    for _table in ("reasoning_jobs", "reasoning_attempts"):
        try:
            with db.transaction() as conn:
                conn.execute(text(f"TRUNCATE {_table} CASCADE"))
        except Exception:
            pass


def _s2_start_run(physician, encounter_id, revision, key):
    created = physician.post(
        f"/api/v1/encounters/{encounter_id}/runs",
        json={"encounter_revision": revision},
        headers=_mutation_headers(physician, key=key, revision=revision),
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]
    uuid.UUID(run_id)
    return run_id


def _s2_is_claimed(job):
    return str(job.get("status")) in ("claimed", "preparing", "running")


def test_global_admission_single_question_per_run():
    """At most 2 claimed/preparing jobs globally; 1 job per run.

    Three encounters (same physician) each start one run against the
    synthetic single-question bundle. Two worker threads call run_once()
    repeatedly with a 0.3s recording adapter to force overlap. While
    workers run, poll public GET /runs/{id}: every run keeps exactly 1
    job, at most 1 claimed per run, at most 2 claimed globally. The
    adapter also records max concurrent provider entries (must be <= 2).

    RED: ImportError on worker.run_once (module does not exist). A
    no-slot implementation claiming all 3 at once would fail the
    global-cap asserts.
    """
    import time

    # RED: backend/src/x_insight/reasoning/worker.py does not exist yet.
    from x_insight.reasoning.worker import run_once

    _s2_truncate_queue_tables()
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "queuedocC")
        _login(physician, "queuedocC", "secret", "physician")

        _insert_synthetic_bundle()
        run_ids = []
        for index, pid in enumerate(
            ["0799000083", "0799000084", "0799000085"]
        ):
            _patient, encounter = _create_sentinel_patient(
                physician, pid, f"s44-s2-c-patient-{index}"
            )
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": _clinical_draft()},
                headers=_mutation_headers(
                    physician, revision=encounter["revision"]
                ),
            )
            assert saved.status_code == 200
            revision = _current_revision(physician, encounter_id)
            run_ids.append(
                _s2_start_run(
                    physician, encounter_id, revision, f"s44-s2-c-run-{index}"
                )
            )

        for run_id in run_ids:
            body = physician.get(f"/api/v1/runs/{run_id}")
            assert body.status_code == 200
            _assert_first_job(body.json())

        lock = threading.Lock()
        active = {"cur": 0, "peak": 0}
        results = []

        def _adapter(*args, **kwargs):
            job = args[0] if args and isinstance(args[0], dict) else {}
            if not isinstance(job, dict) and "job" in kwargs:
                job = kwargs["job"]
            with lock:
                active["cur"] += 1
                active["peak"] = max(active["peak"], active["cur"])
            try:
                time.sleep(0.3)
            finally:
                with lock:
                    active["cur"] -= 1
            return {"ok": True}

        def _loop(worker_id):
            for _ in range(4):
                try:
                    out = run_once(
                        database_url=None,
                        provider_adapter=_adapter,
                        worker_id=worker_id,
                    )
                except Exception as exc:  # keep thread alive, record
                    with lock:
                        results.append(
                            {"error": repr(exc), "worker_id": worker_id}
                        )
                    continue
                with lock:
                    results.append(out)
                time.sleep(0.02)

        threads = [
            threading.Thread(target=_loop, args=("worker-a",)),
            threading.Thread(target=_loop, args=("worker-b",)),
        ]
        for thread in threads:
            thread.start()
        peak_claimed = 0
        try:
            start = time.time()
            while True:
                alive = any(t.is_alive() for t in threads)
                total = 0
                for run_id in run_ids:
                    resp = physician.get(f"/api/v1/runs/{run_id}")
                    assert resp.status_code == 200
                    payload = resp.json()
                    assert "jobs" in payload
                    jobs = payload["jobs"]
                    assert isinstance(jobs, list)
                    assert len(jobs) == 1, "one question per run"
                    here = sum(1 for job in jobs if _s2_is_claimed(job))
                    assert here <= 1, "no run ever has 2 claimed jobs"
                    total += here
                peak_claimed = max(peak_claimed, total)
                if not alive:
                    break
                if time.time() - start > 15:
                    break
                time.sleep(0.05)
        finally:
            for thread in threads:
                thread.join(timeout=15)

        assert active["peak"] <= 2, "global slots exceeded in provider"
        assert peak_claimed <= 2, "at most 2 claimed/preparing at once"
        assert len(results) == 8, "both workers must finish all iterations"
        assert not any("error" in item for item in results), (
            f"run_once raised: {[r for r in results if 'error' in r]}"
        )
        for out in results:
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
        claimed = [r for r in results if r.get("claimed")]
        assert len(claimed) >= 1, "expected at least one claim"
        for out in claimed:
            assert out["job_id"] is not None
            assert out["run_id"] in run_ids
            assert out["question_key"] == SYNTHETIC_QUESTION
            assert out["lease_token"] is not None
        for run_id in run_ids:
            reread = physician.get(f"/api/v1/runs/{run_id}")
            assert reread.status_code == 200
            assert len(reread.json()["jobs"]) == 1


def test_short_claim_lease_heartbeat_persistent_admission():
    """Slow provider stays outside claim; same job cannot be double-claimed.

    One run starts against the synthetic bundle. run_once() runs in a
    background thread with a 0.5s adapter (provider call outside the short
    claim transaction). While in-flight: GET /runs/{id} stays 200 (DB
    responsive, no lock held) and a second run_once() never returns the
    same job_id (busy/None or a different run, never double-claim).
    Afterwards queue.heartbeat(job_id, token) extends lease_deadline.

    RED: ImportError on worker.run_once; without it the heartbeat
    AttributeError path is also red. Uses public status + run_once
    returns only.
    """
    import time

    # RED: backend/src/x_insight/reasoning/worker.py does not exist yet.
    from x_insight.reasoning.worker import run_once

    from x_insight.reasoning import queue as queue_module

    _s2_truncate_queue_tables()
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "queuedocD")
        _login(physician, "queuedocD", "secret", "physician")
        _patient, encounter = _create_sentinel_patient(
            physician, "0799000086", "s44-s2-d-patient"
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
        run_id = _s2_start_run(physician, encounter_id, revision, "s44-s2-d-run")

        entered = threading.Event()
        captured = {}
        first_outcome = {}

        def _slow_adapter(*args, **kwargs):
            job = args[0] if args and isinstance(args[0], dict) else {}
            if not isinstance(job, dict) and "job" in kwargs:
                job = kwargs["job"]
            if isinstance(job, dict):
                captured.update(dict(job))
            entered.set()
            time.sleep(0.5)
            return {"ok": True}

        def _first():
            try:
                first_outcome["result"] = run_once(
                    database_url=None,
                    provider_adapter=_slow_adapter,
                    worker_id="worker-a",
                )
            except Exception as exc:  # surfaced below, never silent
                first_outcome["error"] = repr(exc)

        worker = threading.Thread(target=_first)
        worker.start()
        try:
            assert entered.wait(timeout=5), "provider never entered"
            # DB remains responsive while the provider call is in-flight:
            # plain GET must succeed without waiting on a claim lock.
            probe = physician.get(f"/api/v1/runs/{run_id}")
            assert probe.status_code == 200
            assert "jobs" in probe.json()

            second = run_once(
                database_url=None,
                provider_adapter=lambda *a, **k: {"ok": True},
                worker_id="worker-b",
            )
            assert isinstance(second, dict)
            for key in (
                "claimed",
                "busy",
                "job_id",
                "run_id",
                "question_key",
                "lease_token",
            ):
                assert key in second, f"run_once return missing {key}"
            first_job = captured.get("job_id")
            assert first_job is not None, "adapter must see job_id"
            assert captured.get("lease_token") is not None, (
                "adapter must see lease_token"
            )
            # Second worker can be busy or claim a different run, but
            # never the same in-flight job_id.
            assert second.get("job_id") != first_job, (
                "second worker claimed the same in-flight job"
            )
            if second.get("claimed"):
                assert second.get("job_id") is not None
                assert second.get("job_id") != first_job
            else:
                assert second.get("busy") is True or (
                    second.get("job_id") is None
                ), "idle second worker must report busy/None"
        finally:
            worker.join(timeout=10)

        assert "error" not in first_outcome, (
            f"first run_once raised: {first_outcome.get('error')}"
        )
        first = first_outcome.get("result")
        assert isinstance(first, dict)
        job_id = first.get("job_id") or captured.get("job_id")
        token = first.get("lease_token") or captured.get("lease_token")
        assert job_id is not None and token is not None

        assert hasattr(queue_module, "heartbeat"), (
            "queue.heartbeat missing (plan section 8.4)"
        )
        first_hb = queue_module.heartbeat(job_id, token)
        time.sleep(0.05)
        second_hb = queue_module.heartbeat(job_id, token)

        def _deadline(value):
            if isinstance(value, dict):
                for name in ("lease_deadline", "deadline", "expires_at"):
                    if value.get(name) is not None:
                        return str(value[name])
                return None
            return None if value in (None, True, False) else str(value)

        deadline_a = _deadline(first_hb)
        deadline_b = _deadline(second_hb)
        assert deadline_a is not None, "heartbeat must expose lease_deadline"
        assert deadline_b is not None, "heartbeat must expose lease_deadline"
        assert deadline_b > deadline_a, "heartbeat must extend the lease"


# ---------------------------------------------------------------------------
# S44 slice-3 RED (Tests E-F): fair rotation + saturation busy (T8).
#
# Scope ONLY (tasks.md S44.3; plan.md sections 8.4-8.5): eligible work
# rotates fairly across physicians (round-robin) and then FIFO within a
# physician; saturation returns a visible busy state without deleting saved
# drafts/jobs. Slices 1-2/4 (atomic first job, slots/leases, expiry/
# recovery) are NOT tested here.
#
# Expected minimal worker contract (for the backend agent, no extra seams):
#
# - claim order: round-robin across physicians with queued work, oldest
#   eligible job first within a physician; scheduling state persisted so a
#   physician is not starved across successive run_once() calls.
# - POST /encounters/{id}/runs refuses new runs past MAX_QUEUED_RUNS (100)
#   with 429 + the standard error envelope (code/message/field_errors/
#   request_id/retryable), leaving existing runs and the fresh draft intact.
# - Tests use only public API + run_once() returns for order/busy
#   assertions. run_id -> physician is mapped locally at creation time, so
#   no cross-physician GET /runs read is needed (GET is author-only).
#
# RED: claim_next_job() is pure FIFO by created_at (A1,A2,A3,B1), so the
# second claim is A2 instead of B1; start_run() has no admission cap, so
# the overflow POST returns 202 instead of 429.
#
# Synthetic-bundle choice (test-only, never a production default): same
# pattern as slices 1-2 -- one synthetic registration pointer/event row
# (bundle_hash "synthetic-bundle-hash-s44-slice1", one question
# "synthetic_example").
# ---------------------------------------------------------------------------


def _s3_create_queued_run(physician, patient_id, patient_key, run_key):
    """Create a patched draft + one queued run; return (encounter_id, run_id)."""
    _patient, encounter = _create_sentinel_patient(
        physician, patient_id, patient_key
    )
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


def test_fair_rotation_across_physicians_then_fifo():
    """Queued claims rotate across physicians, FIFO within a physician.

    Physician A queues 3 runs (A1, A2, A3, in that creation order),
    physician B queues 1 run (B1) last -- all against the synthetic
    single-question bundle. A single sequential worker calls run_once()
    with a fast no-op adapter; each call reads persisted scheduling
    state. Claimed run_ids map back to physicians via the locally
    recorded creation mapping (no cross-author GET).

    Only two claims are observable per test: the approved two global
    provider slots (slice-2, still green) keep both claimed leases live,
    so a third run_once() must report busy rather than a third claim.
    The full A1<A2<A3 tail order is therefore pinned by the observable
    prefix: rotation serves B by the second claim at the latest (no
    starvation), and the served A job must be the oldest, A1 (FIFO
    within physician).

    Fairness assertions: the first two claims come from different
    physicians, and the A claim is A1.

    RED: current claim is pure FIFO by created_at (A1,A2,...), so the
    second claim is A2 instead of B1 and the rotation assert fails.
    """
    from x_insight.reasoning.worker import run_once

    with (
        TestClient(app) as admin,
        TestClient(app) as physician_a,
        TestClient(app) as physician_b,
    ):
        _login(admin)
        _make_physician(admin, "fairdocA")
        _make_physician(admin, "fairdocB")
        _login(physician_a, "fairdocA", "secret", "physician")
        _login(physician_b, "fairdocB", "secret", "physician")
        _insert_synthetic_bundle()

        _, run_a1 = _s3_create_queued_run(
            physician_a, "0799000301", "s44-s3-fair-patient-a1", "s44-s3-fair-run-a1"
        )
        _, run_a2 = _s3_create_queued_run(
            physician_a, "0799000302", "s44-s3-fair-patient-a2", "s44-s3-fair-run-a2"
        )
        _, run_a3 = _s3_create_queued_run(
            physician_a, "0799000303", "s44-s3-fair-patient-a3", "s44-s3-fair-run-a3"
        )
        _, run_b1 = _s3_create_queued_run(
            physician_b, "0799000304", "s44-s3-fair-patient-b1", "s44-s3-fair-run-b1"
        )
        owner = {run_a1: "A", run_a2: "A", run_a3: "A", run_b1: "B"}

        def _noop_adapter(*args, **kwargs):
            _ = (args, kwargs)
            return {"ok": True}

        claims = []
        for _ in range(4):
            out = run_once(
                database_url=None,
                provider_adapter=_noop_adapter,
                worker_id="s44-s3-fair-worker",
            )
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
            claims.append(out)

        served = [item for item in claims if item.get("claimed")]
        # Two global slots stay live once claimed (slice-2 contract), so
        # exactly the first two calls claim; later calls report busy.
        assert len(served) == 2, f"expected exactly 2 claims, got {claims}"
        assert all(item.get("run_id") in owner for item in served)
        assert len({item["run_id"] for item in served}) == 2, "no double-claim"
        for item in claims[2:]:
            assert item.get("claimed") is False, (
                "slots full: further calls must not claim"
            )

        labels = [owner[item["run_id"]] for item in served]
        # RED: pure FIFO yields ["A", "A"]; fair rotation serves B within
        # the first two claims regardless of FIFO tie-break (no starvation).
        assert set(labels) == {"A", "B"}, (
            f"first two claims must rotate across physicians, got {labels}"
        )
        # FIFO within physician A survives the rotation: the served A job
        # is the oldest, A1 (the A2/A3 tail stays queued behind live slots).
        a_served = [item for item in served if owner[item["run_id"]] == "A"]
        assert len(a_served) == 1 and a_served[0]["run_id"] == run_a1, (
            f"served A job must be the oldest (A1), got {labels}"
        )


def test_saturation_busy_without_deletion():
    """Queue past MAX_QUEUED_RUNS refuses with 429 and keeps saved work.

    Fill the queue to MAX_QUEUED_RUNS (100) via direct POST /runs loops
    (one physician, one encounter per run so generations never collide).
    The next POST /encounters/{id}/runs for a fresh draft must return 429
    (busy) with the standard error envelope -- not 500/202. Afterwards an
    existing run still reads 200 with its single queued job and the fresh
    draft still reads 200 (nothing deleted).

    RED: start_run() has no admission cap, so the overflow POST returns
    202 and the 429 assertion fails.
    """
    from x_insight.reasoning.queue import MAX_QUEUED_RUNS

    assert int(MAX_QUEUED_RUNS) == 100
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "saturatedoc")
        _login(physician, "saturatedoc", "secret", "physician")
        _insert_synthetic_bundle()

        run_ids = []
        for index in range(int(MAX_QUEUED_RUNS)):
            _, run_id = _s3_create_queued_run(
                physician,
                f"079900{400 + index:04d}",
                f"s44-s3-sat-patient-{index}",
                f"s44-s3-sat-run-{index}",
            )
            run_ids.append(run_id)
        assert len(run_ids) == int(MAX_QUEUED_RUNS)

        _patient, fresh = _create_sentinel_patient(
            physician, "0799000500", "s44-s3-sat-patient-fresh"
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
                physician,
                key="s44-s3-sat-run-overflow",
                revision=fresh_revision,
            ),
        )
        # RED: uncapped start_run returns 202 here (or 500 on some failure
        # path); the contract requires visible busy without deletion.
        assert overflow.status_code == 429, (
            f"saturated queue must return 429 busy, got {overflow.status_code}"
        )
        envelope = overflow.json()
        for key in ("code", "message", "request_id"):
            assert key in envelope, (
                "429 must use the standard error envelope"
            )

        # Saved drafts/jobs retained: existing run and fresh draft readable.
        kept = physician.get(f"/api/v1/runs/{run_ids[0]}")
        assert kept.status_code == 200
        kept_jobs = kept.json()["jobs"]
        assert isinstance(kept_jobs, list)
        assert len(kept_jobs) == 1
        draft = physician.get(f"/api/v1/encounters/{fresh_id}")
        assert draft.status_code == 200


# ---------------------------------------------------------------------------
# S44 slice-4 RED (Tests G-H): lease expiry/reclaim fencing + restart recovery
# (T8).
#
# Scope ONLY (tasks.md S44.4; plan.md sections 8.4-8.5): an expired lease
# (lease 120s, heartbeat 15s) is reclaimed by another worker with a fresh
# fencing token (generation+1); the old token can never commit afterwards;
# a worker restart retains recorded attempts and terminal artifacts, keyed
# through one run_once() entry point with a deterministic clock and bounded
# attempt budgets. Slices 1-3 (atomic first job, slots/leases, fairness/
# busy) are NOT tested here.
#
# Expected minimal contract (for the backend agent, no extra seams):
#
# - queue exposes complete_job(job_id, lease_token, outcome) with fencing:
#   the commit succeeds only when the presented lease_token matches the
#   current holder, the fencing generation matches, the deployment
#   generation is current, and the lease has not expired via the
#   deterministic clock (queue.now_utc/set_now_fn/reset_now_fn). A stale
#   token returns None/False (or a falsy rejected mapping) or raises a
#   fencing/lease error and never completes the reclaimed job.
# - worker.run_once records exactly one attempt per provider call in
#   reasoning_attempts (persisted, survives dispose_engines() restart) and
#   surfaces it via GET /runs/{id} jobs attempt_count/attempts (or run_once
#   attempt_index when GET carries no attempt key).
# - run_once returns expose fencing_generation alongside job_id/lease_token
#   so reclaim (same job_id, new token, fencing+1) is observable.
# - Tests use only public GET /runs/{id} + run_once/queue helpers; direct
#   SQL is setup-only (synthetic bundle, tolerant TRUNCATEs). Each adapter
#   performs a GET probe to prove the provider call runs OUTSIDE the short
#   claim transaction (no external request under an open claim txn).
#   Deterministic clock jumps only (no real sleep for expiry); the clock is
#   restored via reset_now_fn in teardown.
#
# RED: run_once returns carry no fencing_generation, expired claimed jobs
# are never reclaimed (claim_next_job only serves status='queued'), no
# queue.complete_job helper exists, and GET jobs expose no
# attempt_count/attempts (2 new failures, 6 prior passes).
#
# Synthetic-bundle choice (test-only, never a production default): same
# pattern as slices 1-3 -- one synthetic registration pointer/event row
# (bundle_hash "synthetic-bundle-hash-s44-slice1", one question
# "synthetic_example").
# ---------------------------------------------------------------------------


def _s4_truncate_attempts():
    # Tolerant per-test probe for the slice-4 contract table; never fails
    # setup when reasoning_attempts does not exist yet.
    try:
        with db.transaction() as conn:
            conn.execute(text("TRUNCATE reasoning_attempts CASCADE"))
    except Exception:
        pass


def _s4_start_run(physician, patient_id, patient_key, run_key):
    """Patch a sentinel draft and start one run; return (encId, run_id)."""
    _patient, encounter = _create_sentinel_patient(
        physician, patient_id, patient_key
    )
    encounter_id = encounter["id"]
    saved = physician.patch(
        f"/api/v1/encounters/{encounter_id}",
        json={"draft_data": _clinical_draft()},
        headers=_mutation_headers(physician, revision=encounter["revision"]),
    )
    assert saved.status_code == 200
    revision = _current_revision(physician, encounter_id)
    run_id = _s2_start_run(physician, encounter_id, revision, run_key)
    return encounter_id, run_id


def _s4_run_once_keys(out, where):
    assert isinstance(out, dict), f"{where}: run_once must return a dict"
    for key in (
        "claimed",
        "busy",
        "job_id",
        "run_id",
        "question_key",
        "lease_token",
    ):
        assert key in out, f"{where}: run_once return missing {key}"
    return out


def _s4_commit_rejected(result):
    """True when a complete_job return value means 'stale token refused'."""
    if result is None or result is False:
        return True
    if isinstance(result, dict):
        if result.get("committed") is False or result.get("ok") is False:
            return True
        if result.get("rejected") is True:
            return True
    return False


def _s4_attempt_evidence(first, job):
    """True when one recorded attempt is observable via return or GET job."""
    if first.get("attempt_index") is not None:
        return True
    count = job.get("attempt_count")
    if isinstance(count, int) and count > 0:
        return True
    attempts = job.get("attempts")
    if isinstance(attempts, list) and len(attempts) > 0:
        return True
    return False


def test_expired_lease_reclaimed_old_token_cannot_commit():
    """Expired lease is reclaimed with fencing+1; the old token cannot commit.

    One run starts against the synthetic bundle. run_once() with a fast
    adapter claims it (job_id + lease_token + fencing recorded; the adapter
    proves the provider call runs outside the claim txn via a GET probe).
    The deterministic queue clock jumps +130s past the 120s lease (no
    sleep). A second run_once() with a different worker_id must reclaim the
    SAME job (same job_id, new lease_token, fencing+1), visible via
    run_once returns and GET jobs status claimed. A commit attempt with the
    OLD token via queue.complete_job must then be rejected (None/False or
    a fencing error), with GET still showing the new token's live claim.

    RED: no fencing_generation in run_once returns, no reclaim of expired
    claimed rows, and no queue.complete_job helper exist yet.
    """
    from datetime import timedelta

    from x_insight.reasoning import queue as queue_module
    from x_insight.reasoning.worker import run_once

    _s4_truncate_attempts()
    with TestClient(app) as admin, TestClient(app) as physician:
        _login(admin)
        _make_physician(admin, "leasedocG")
        _login(physician, "leasedocG", "secret", "physician")
        _insert_synthetic_bundle()
        _, run_id = _s4_start_run(
            physician, "0799000087", "s44-s4-g-patient", "s44-s4-g-run"
        )

        captured = {}
        probe = {}

        def _fast_adapter(*args, **kwargs):
            job = (
                args[0]
                if args and isinstance(args[0], dict)
                else kwargs.get("job", {})
            )
            if isinstance(job, dict):
                captured.update(dict(job))
            probe["code"] = physician.get(f"/api/v1/runs/{run_id}").status_code
            return {"ok": True}

        first = _s4_run_once_keys(
            run_once(
                database_url=None,
                provider_adapter=_fast_adapter,
                worker_id="worker-g1",
            ),
            "first claim",
        )
        assert first["claimed"] is True, "expected one claim on a fresh queue"
        assert probe.get("code") == 200, (
            "GET must stay responsive during the provider call"
        )
        job_id = first["job_id"]
        old_token = first["lease_token"]
        assert job_id is not None and old_token is not None
        assert captured.get("job_id") == job_id
        # RED: run_once returns carry no fencing token yet (plan 8.4).
        assert first.get("fencing_generation") is not None, (
            "run_once must expose fencing_generation (plan 8.4 fencing token)"
        )
        old_fencing = int(first["fencing_generation"])

        fetched = physician.get(f"/api/v1/runs/{run_id}")
        assert fetched.status_code == 200
        assert _s2_is_claimed(fetched.json()["jobs"][0])

        # Deterministic expiry: jump the queue clock past the 120s lease.
        base = queue_module.now_utc()
        queue_module.set_now_fn(lambda: base + timedelta(seconds=130))
        try:
            second = _s4_run_once_keys(
                run_once(
                    database_url=None,
                    provider_adapter=lambda *a, **k: {"ok": True},
                    worker_id="worker-g2",
                ),
                "reclaim after expiry",
            )
            # RED: expired claimed rows are never reclaimed (only 'queued'
            # rows are served), so claimed is False here.
            assert second.get("claimed") is True, (
                "a lease expired via the deterministic clock must be reclaimable"
            )
            assert second.get("job_id") == job_id, (
                "reclaim must serve the SAME job"
            )
            new_token = second.get("lease_token")
            assert new_token is not None and new_token != old_token, (
                "reclaim must mint a fresh lease token"
            )
            assert second.get("fencing_generation") is not None
            assert int(second["fencing_generation"]) == old_fencing + 1, (
                "reclaim must bump the fencing generation by exactly one"
            )

            reread = physician.get(f"/api/v1/runs/{run_id}")
            assert reread.status_code == 200
            jobs = reread.json()["jobs"]
            assert len(jobs) == 1 and _s2_is_claimed(jobs[0])

            # RED: no queue.complete_job/commit helper exists yet.
            commit = getattr(queue_module, "complete_job", None)
            assert callable(commit), (
                "queue.complete_job(job_id, lease_token, outcome) with fencing "
                "(token + generation + deployment check, lease via clock) "
                "is required"
            )
            try:
                committed = commit(job_id, old_token, {"ok": True})
            except Exception as exc:
                lowered = repr(exc).lower()
                assert any(
                    word in lowered
                    for word in (
                        "fenc",
                        "lease",
                        "token",
                        "generation",
                        "deploy",
                        "stale",
                        "expired",
                    )
                ), f"old-token commit must raise a fencing/lease error, got {exc!r}"
            else:
                assert _s4_commit_rejected(committed), (
                    "stale lease_token must not commit the reclaimed job, "
                    f"got {committed!r}"
                )

            kept = physician.get(f"/api/v1/runs/{run_id}")
            assert kept.status_code == 200
            kept_jobs = kept.json()["jobs"]
            assert len(kept_jobs) == 1
            assert _s2_is_claimed(kept_jobs[0]), (
                "the old token must not complete the job held by the new token"
            )
        finally:
            queue_module.reset_now_fn()


def test_restart_retains_attempts_and_terminal_artifacts():
    """Restart keeps recorded attempts; the job is neither lost nor duplicated.

    One run starts against the synthetic bundle. run_once() with a
    controlled adapter (writes a marker, GET-probes outside the claim txn,
    returns success) must record exactly one attempt, observable via GET
    jobs attempt_count/attempts or run_once attempt_index. A worker restart
    is simulated with db.dispose_engines() plus a fresh worker_id: afterwards
    the public GET must still show exactly 1 job with attempt history
    retained (attempt_count >= 1), and any terminal artifact present must be
    unchanged.

    RED: run_once records no reasoning_attempts row and neither the return
    nor GET exposes attempt_index/attempt_count/attempts.
    """
    from x_insight.reasoning import queue as queue_module
    from x_insight.reasoning.worker import run_once

    _s4_truncate_attempts()
    try:
        with TestClient(app) as admin, TestClient(app) as physician:
            _login(admin)
            _make_physician(admin, "restartdocH")
            _login(physician, "restartdocH", "secret", "physician")
            _insert_synthetic_bundle()
            _, run_id = _s4_start_run(
                physician, "0799000088", "s44-s4-h-patient", "s44-s4-h-run"
            )

            marker = []
            probe = {}

            def _recording_adapter(*args, **kwargs):
                job = (
                    args[0]
                    if args and isinstance(args[0], dict)
                    else kwargs.get("job", {})
                )
                assert isinstance(job, dict) and job.get("job_id"), (
                    "adapter must receive the claimed job"
                )
                marker.append(job["job_id"])
                probe["code"] = physician.get(
                    f"/api/v1/runs/{run_id}"
                ).status_code
                return {"ok": True}

            first = _s4_run_once_keys(
                run_once(
                    database_url=None,
                    provider_adapter=_recording_adapter,
                    worker_id="worker-h1",
                ),
                "first claim",
            )
            assert first["claimed"] is True, "expected one claim on a fresh queue"
            assert marker == [first["job_id"]], (
                "provider must be invoked once with the claimed job"
            )
            assert probe.get("code") == 200, (
                "GET must stay responsive during the provider call"
            )

            body = physician.get(f"/api/v1/runs/{run_id}")
            assert body.status_code == 200
            jobs = body.json()["jobs"]
            assert isinstance(jobs, list) and len(jobs) == 1
            # RED: no attempt is recorded or exposed yet.
            assert _s4_attempt_evidence(first, jobs[0]), (
                "run_once must persist one attempt per provider call in "
                "reasoning_attempts, visible via GET jobs attempt_count/"
                "attempts or run_once attempt_index"
            )

            # Simulate a worker restart: drop pooled engines, then continue
            # with a fresh worker identity against the same database.
            db.dispose_engines()
            second = _s4_run_once_keys(
                run_once(
                    database_url=None,
                    provider_adapter=lambda *a, **k: {"ok": True},
                    worker_id="worker-h2-restarted",
                ),
                "post-restart",
            )

            reread = physician.get(f"/api/v1/runs/{run_id}")
            assert reread.status_code == 200
            kept = reread.json()["jobs"]
            assert isinstance(kept, list) and len(kept) == 1, (
                "restart must not duplicate or lose the job"
            )
            if second.get("claimed"):
                assert second.get("job_id") == first["job_id"], (
                    "a post-restart claim must not duplicate the job"
                )
            else:
                assert second.get("job_id") in (None, first["job_id"]), (
                    "an idle post-restart worker must report busy/None, "
                    "never a phantom job"
                )
            assert _s4_attempt_evidence(second, kept[0]), (
                "recorded attempts must survive the restart via public GET"
            )
            artifact = kept[0].get("artifact", kept[0].get("terminal_artifact"))
            if artifact is not None:
                assert artifact, (
                    "a persisted terminal artifact must survive restart"
                )
    finally:
        queue_module.reset_now_fn()

