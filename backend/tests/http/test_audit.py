"""S52 slice 1 (RED): mutation + audit commit atomically; failures claim no success.

Scope: plan.md S52 item 1; seam T1 only (authenticated HTTP against real
PostgreSQL, plus the existing GET /api/v1/audit-events read seam for
assertions).

Behavior under test:
- Admin POST /api/v1/physicians (CSRF + Idempotency-Key) -> 201 and a
  physician.create audit event with result_reference == new account id
  and actor_id == admin id.
- Replaying the SAME Idempotency-Key with a DIFFERENT body
  (different username) -> 409, and no second physician.create success
  event for the new username (either no new event, or no 2xx
  result_status on it).
- A failed login (wrong password) -> 401 and no auth.login_success
  event for that account (a login_failure event may exist).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_audit():
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


def headers(client, key):
    return {
        "X-CSRF-Token": client.cookies.get("xinsight_csrf"),
        "Idempotency-Key": key,
    }


def audit_items(client, operation):
    response = client.get(
        "/api/v1/audit-events", params={"operation": operation, "limit": 100}
    )
    assert response.status_code == 200
    return response.json()["items"]


def is_success(event):
    status = event.get("result_status")
    return status is not None and 200 <= int(status) < 300


def test_successful_mutation_and_audit_commit_atomically_and_failure_claims_no_success():
    with TestClient(app) as admin:
        login(admin)
        admin_id = admin.get("/api/v1/me").json()["id"]

        # 1. Successful mutation commits its audit event atomically.
        created = admin.post(
            "/api/v1/physicians",
            json={"username": "auditdoctor", "password": "synthetic-secret-one"},
            headers=headers(admin, "s52-audit-once"),
        )
        assert created.status_code == 201
        account_id = created.json()["id"]

        creates = audit_items(admin, "physician.create")
        assert any(
            event["operation"] == "physician.create"
            and event["result_reference"] == account_id
            and event["actor_id"] == admin_id
            for event in creates
        )
        creates_before = len(creates)
        success_before = audit_items(admin, "auth.login_success")

        # 2. Same key + different body conflicts and claims no new success.
        conflict = admin.post(
            "/api/v1/physicians",
            json={"username": "auditintruder", "password": "synthetic-secret-one"},
            headers=headers(admin, "s52-audit-once"),
        )
        assert conflict.status_code == 409

        creates_after = audit_items(admin, "physician.create")
        assert len(creates_after) == creates_before
        for event in creates_after:
            if event.get("target_display") == "auditintruder":
                assert not is_success(event)

        # 3. Failed login records no success for that account.
        denied = admin.post(
            "/api/v1/auth/login",
            json={
                "username": "auditdoctor",
                "password": "wrong-secret",
                "role": "physician",
            },
        )
        assert denied.status_code == 401

        success_after = audit_items(admin, "auth.login_success")
        assert [
            event
            for event in success_after
            if event.get("result_reference") == account_id
        ] == [
            event
            for event in success_before
            if event.get("result_reference") == account_id
        ]


def test_retry_and_renamed_account_histories_are_attributed_without_record_bodies(
    monkeypatch,
):
    """S52 slice 2 (RED): retry + renamed-account audit attribution (T1/T8).

    Scope: plan.md S52 item 2; seams T1 (authenticated HTTP against real
    PostgreSQL) + T8 (real worker entry point). Synthetic single-question
    bundle/provider only, never BNs/, never clinical.

    Behavior under test:
    - Admin creates a physician, then renames it via PATCH. The ORIGINAL
      physician.create event keeps the ORIGINAL display snapshot and the
      same account id (stable history, not rewritten); a physician.edit
      event references the same id.
    - A failed run retried via POST /runs/{id}/retry (-> 202) leaves a
      run.retry audit event referencing the run id (expected RED: the
      retry path in B/reasoning/runs.py records no audit event).
    - Audit HTTP exposes only safe columns (no result_payload/result_status
      bodies, no password/API-key material); items carry references
      (result_reference) rather than record bodies.
    """

    import hashlib
    import http.server
    import json
    import socketserver
    import threading
    from pathlib import Path

    history_dir = (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "content"
        / "history"
    )
    monkeypatch.setenv("X_INSIGHT_HISTORY_CONTENT_DIR", str(history_dir))
    monkeypatch.setenv("X_INSIGHT_PROVIDER_ALLOW_LOCAL", "true")

    ORIG = "s52retrydoc"
    RENAMED = "s52renameddoc"
    SECRET = "synthetic-s52-secret-one"
    API_KEY = "synthetic-provider-key-s52-001"
    QUESTION = "s52_q1"
    BUNDLE_HASH = "synthetic-bundle-hash-s52-slice2"
    NETWORK_VERSION = "v1"
    HISTORY_VERSION = "synthetic-history-v1"
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

    def mheaders(client, key=None, revision=None):
        headers = {"X-CSRF-Token": client.cookies.get("xinsight_csrf")}
        if key is not None:
            headers["Idempotency-Key"] = key
        if revision is not None:
            headers["If-Match"] = str(revision)
        return headers

    def insert_bundle():
        pins = {
            "questions": [
                {
                    "question_key": QUESTION,
                    "version": NETWORK_VERSION,
                    "network_hash": NETWORK_HASH,
                    "network_xml": SYNTHETIC_XML.decode("utf-8"),
                    "prompt": (
                        "SYNTH-S52 estimate every CPT as percentages "
                        "summing to 100 using only listed patient facts."
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
                    "VALUES ('registration', 1, :hash, CAST(:pins AS jsonb)) "
                    "ON CONFLICT (workflow) DO UPDATE SET revision = 1, "
                    "bundle_hash = :hash, pins = CAST(:pins AS jsonb)"
                ),
                {"hash": BUNDLE_HASH, "pins": json.dumps(pins)},
            )
            conn.execute(
                text(
                    "INSERT INTO model_bundle_events "
                    "(workflow, revision, bundle_hash, pins, action) "
                    "VALUES ('registration', 1, :hash, CAST(:pins AS jsonb), "
                    "'activate') ON CONFLICT (workflow, revision) DO NOTHING"
                ),
                {"hash": BUNDLE_HASH, "pins": json.dumps(pins)},
            )

    def insert_provider_config(base_url):
        from x_insight.reasoning.provider_config import encrypt_api_key

        ciphertext = encrypt_api_key(API_KEY)
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
                        "model": "synthetic-model-s52",
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

    def start_failing_provider():
        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                out = json.dumps(
                    {"error": "synthetic provider failure - test only"}
                ).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *args):
                pass

        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
        server.daemon_threads = True
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05}
        )
        thread.daemon = True
        thread.start()
        return server, thread

    def drain_failures(worker_prefix, max_steps=15):
        from datetime import timedelta

        from x_insight.reasoning import queue as queue_module
        from x_insight.reasoning.worker import run_once as _real_run_once

        outcomes = []
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
                    outcomes.append({"claimed": True, "raised": type(exc).__name__})
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

    def clinical_draft():
        return {
            "diagnosis": {"answers": {"synthetic_item": "synthetic_value"}},
            "history": {
                "definition_version": HISTORY_VERSION,
                "values": {
                    "synthetic_flag_true": {"status": "known", "value": True},
                },
            },
            "effects": {
                "definition_version": HISTORY_VERSION,
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
            "medications": [{"catalog_drug_id": "synthetic-s52-med-a"}],
            "ddi_report": {
                "dataset_version": "synthetic-ddi-s52",
                "medication_fingerprint": "fp-synth-s52",
            },
        }

    def current_revision(physician, encounter_id):
        fetched = physician.get(f"/api/v1/encounters/{encounter_id}")
        assert fetched.status_code == 200
        return int(fetched.json()["encounter"]["revision"])

    insert_bundle()
    server, thread = start_failing_provider()
    try:
        host, port = server.server_address
        insert_provider_config(f"http://{host}:{port}")
        with TestClient(app) as admin, TestClient(app) as physician:
            login(admin)
            admin_id = admin.get("/api/v1/me").json()["id"]

            # 1. Rename attribution: create, snapshot, rename, re-read.
            created = admin.post(
                "/api/v1/physicians",
                json={"username": ORIG, "password": SECRET},
                headers=mheaders(admin, key="s52-s2-create"),
            )
            assert created.status_code == 201
            account_id = created.json()["id"]

            creates = audit_items(admin, "physician.create")
            create_event = next(
                event
                for event in creates
                if event.get("result_reference") == account_id
            )
            assert create_event["actor_id"] == admin_id
            assert create_event["actor_display"] == "admin"
            original_display = create_event["target_display"]
            assert original_display == ORIG

            renamed = admin.patch(
                f"/api/v1/physicians/{account_id}",
                json={"username": RENAMED},
                headers=mheaders(
                    admin, key="s52-s2-rename", revision=created.headers["etag"]
                ),
            )
            assert renamed.status_code == 200
            assert renamed.json()["id"] == account_id
            assert renamed.json()["username"] == RENAMED

            creates_after = audit_items(admin, "physician.create")
            original = next(
                event
                for event in creates_after
                if event.get("result_reference") == account_id
            )
            assert original["target_display"] == original_display
            assert original["target_display"] == ORIG
            assert original["result_reference"] == account_id

            edits = audit_items(admin, "physician.edit")
            assert any(
                event.get("result_reference") == account_id for event in edits
            )

            # 2. Failed run -> manual retry through public HTTP + worker.
            login(physician, RENAMED, SECRET, "physician")
            patient_response = physician.post(
                "/api/v1/patients",
                json={
                    "first_name": "Anna",
                    "last_name": "Muller",
                    "sex": "F",
                    "age": 30,
                    "patient_id": "0799000521",
                    "clinical_status": "first_time",
                },
                headers=mheaders(physician, key="s52-s2-patient"),
            )
            assert patient_response.status_code == 201
            encounter = patient_response.json()["encounter"]
            encounter_id = encounter["id"]
            saved = physician.patch(
                f"/api/v1/encounters/{encounter_id}",
                json={"draft_data": clinical_draft()},
                headers=mheaders(physician, revision=encounter["revision"]),
            )
            assert saved.status_code == 200
            revision = current_revision(physician, encounter_id)
            started = physician.post(
                f"/api/v1/encounters/{encounter_id}/runs",
                json={"encounter_revision": revision},
                headers=mheaders(physician, key="s52-s2-run", revision=revision),
            )
            assert started.status_code == 202
            run_id = started.json()["run_id"]

            drain_failures("s52-s2", max_steps=15)
            failed = physician.get(f"/api/v1/runs/{run_id}")
            assert failed.status_code == 200
            failed_body = failed.json()
            assert failed_body["run"]["status"] == "failed"
            failed_jobs = [
                job
                for job in failed_body["jobs"]
                if job["question_key"] == QUESTION
            ]
            assert len(failed_jobs) == 1
            assert failed_jobs[0]["status"] == "failed"
            run_revision = int(failed_body["run"]["revision"])

            retried = physician.post(
                f"/api/v1/runs/{run_id}/retry",
                json={
                    "question_key": QUESTION,
                    "failed_stage": "estimating_cpts",
                    "expected_run_revision": run_revision,
                },
                headers=mheaders(physician, key="s52-s2-retry"),
            )
            assert retried.status_code == 202

            starts = audit_items(admin, "run.start")
            assert any(
                event.get("result_reference") == run_id for event in starts
            )

            # RED: no run.retry event is recorded on the retry path.
            retries = audit_items(admin, "run.retry")
            assert any(
                event.get("result_reference") == run_id for event in retries
            )

            # 3. No record bodies or key material through the audit seam.
            raw = admin.get("/api/v1/audit-events", params={"limit": 100})
            assert raw.status_code == 200
            for secret in (
                SECRET,
                API_KEY,
                "password_hash",
                "request_hash",
                "key_ciphertext",
                "pbkdf2",
            ):
                assert secret not in raw.text
            for item in raw.json()["items"]:
                assert "result_payload" not in item
                assert "result_status" not in item
                assert "password" not in json.dumps(item)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_admin_filters_paginate_detail_and_physician_denied_and_append_only():
    """S52 slice 3 (RED): audit filters/pagination/detail/denials/append-only.

    Scope: plan.md S52 item 3; seams T1 (authenticated HTTP against real
    PostgreSQL) + migration/operations (direct-SQL append-only guard check,
    explicitly allowed by the plan card).

    Behavior under test (dictated slice-3 contract):
    - GET /api/v1/audit-events gains actor_id/since/until/target filters
      alongside the existing operation/limit/cursor parameters.
    - GET /api/v1/audit-events/{id} returns the single event (admin-only,
      details present as an object).
    - No write interface on /api/v1/audit-events* (404/405).
    - audit_events is append-only at the migration level (UPDATE/DELETE
      fail, INSERT and fixture TRUNCATE still work).
    """

    from datetime import datetime

    USER_A = "s52filtera"
    USER_B = "s52filterb"
    SECRET = "synthetic-s52-filter-secret-one"

    def _parse(ts):
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))

    with (
        TestClient(app) as admin,
        TestClient(app) as phys_a,
        TestClient(app) as anon,
    ):
        # 1. Admin creates two physicians; physician A logs in.
        login(admin)
        created_a = admin.post(
            "/api/v1/physicians",
            json={"username": USER_A, "password": SECRET},
            headers=headers(admin, "s52-s3-create-a"),
        )
        assert created_a.status_code == 201
        a_id = created_a.json()["id"]
        created_b = admin.post(
            "/api/v1/physicians",
            json={"username": USER_B, "password": SECRET},
            headers=headers(admin, "s52-s3-create-b"),
        )
        assert created_b.status_code == 201
        b_id = created_b.json()["id"]
        login(phys_a, USER_A, SECRET, "physician")

        # 2. Physician denied, anonymous unauthenticated.
        assert phys_a.get("/api/v1/audit-events").status_code == 403
        assert anon.get("/api/v1/audit-events").status_code == 401

        # 3. Filters.
        by_actor = admin.get(
            "/api/v1/audit-events", params={"actor_id": a_id, "limit": 100}
        )
        assert by_actor.status_code == 200
        actor_items = by_actor.json()["items"]
        assert len(actor_items) >= 1
        assert all(item.get("actor_id") == a_id for item in actor_items)
        assert any(
            item.get("operation") == "auth.login_success" for item in actor_items
        )

        by_op = admin.get(
            "/api/v1/audit-events",
            params={"operation": "physician.create", "limit": 100},
        )
        assert by_op.status_code == 200
        op_items = by_op.json()["items"]
        assert len(op_items) >= 2
        assert all(
            item.get("operation") == "physician.create" for item in op_items
        )

        by_target = admin.get(
            "/api/v1/audit-events", params={"target": USER_B, "limit": 100}
        )
        assert by_target.status_code == 200
        assert any(
            item.get("result_reference") == b_id
            for item in by_target.json()["items"]
        )

        since, until = "2000-01-01T00:00:00Z", "2100-01-01T00:00:00Z"
        windowed = admin.get(
            "/api/v1/audit-events",
            params={"since": since, "until": until, "limit": 100},
        )
        assert windowed.status_code == 200
        lo, hi = _parse(since), _parse(until)
        for item in windowed.json()["items"]:
            assert lo <= _parse(item["occurred_at"]) <= hi

        # 4. Pagination: limit=1 covers distinct ids with stable ordering.
        page1 = admin.get("/api/v1/audit-events", params={"limit": 1})
        assert page1.status_code == 200
        body1 = page1.json()
        assert len(body1["items"]) == 1
        assert body1["next_cursor"] is not None
        page2 = admin.get(
            "/api/v1/audit-events",
            params={"limit": 1, "cursor": body1["next_cursor"]},
        )
        assert page2.status_code == 200
        body2 = page2.json()
        assert len(body2["items"]) == 1
        assert body2["items"][0]["id"] != body1["items"][0]["id"]
        first = (_parse(body1["items"][0]["occurred_at"]), body1["items"][0]["id"])
        second = (
            _parse(body2["items"][0]["occurred_at"]),
            body2["items"][0]["id"],
        )
        assert first <= second

        # 5. Detail: admin sees the event, physician is denied.
        b_create_id = next(
            item["id"] for item in op_items if item.get("result_reference") == b_id
        )
        detail = admin.get(f"/api/v1/audit-events/{b_create_id}")
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["id"] == b_create_id
        assert detail_body["operation"] == "physician.create"
        assert detail_body["result_reference"] == b_id
        assert isinstance(detail_body.get("details"), dict)
        assert phys_a.get(f"/api/v1/audit-events/{b_create_id}").status_code == 403

        # 6. No write interface.
        for method in ("post", "patch"):
            response = getattr(admin, method)("/api/v1/audit-events", json={})
            assert response.status_code in (404, 405)
        response = admin.request("DELETE", "/api/v1/audit-events")
        assert response.status_code in (404, 405)

        # 7. Append-only operations check (direct SQL, migration seam).
        engine = db.get_engine()
        with engine.connect() as conn:
            row_id = conn.execute(text("SELECT id FROM audit_events LIMIT 1")).scalar()
            assert row_id is not None
            try:
                conn.execute(
                    text("UPDATE audit_events SET target_display='x' WHERE id=:id"),
                    {"id": row_id},
                )
            except Exception:
                conn.rollback()
                update_blocked = True
            else:
                conn.rollback()
                update_blocked = False
            can_update = conn.execute(
                text(
                    "SELECT has_table_privilege("
                    "current_user, 'audit_events', 'UPDATE')"
                )
            ).scalar()
            trigger_count = conn.execute(
                text(
                    "SELECT count(*) FROM pg_trigger WHERE tgrelid = "
                    "'audit_events'::regclass AND NOT tgisinternal"
                )
            ).scalar()
            rule_count = conn.execute(
                text("SELECT count(*) FROM pg_rules WHERE tablename = 'audit_events'")
            ).scalar()
            mechanism_documented = (
                (can_update is False)
                or (trigger_count or 0) > 0
                or (rule_count or 0) > 0
            )
            if not update_blocked:
                pytest.fail(
                    "audit_events allows UPDATE "
                    f"(can_update={can_update}, triggers={trigger_count}, "
                    f"rules={rule_count})"
                )
            assert mechanism_documented, (
                "UPDATE blocked but no append-only guard "
                "(privilege/trigger/rule) is visible"
            )
            try:
                conn.execute(
                    text("DELETE FROM audit_events WHERE id=:id"), {"id": row_id}
                )
            except Exception:
                conn.rollback()
            else:
                conn.rollback()
                pytest.fail("audit_events allows DELETE")
            conn.execute(
                text("INSERT INTO audit_events (operation) VALUES ('s52.append_probe')")
            )
            conn.rollback()
        with db.transaction() as conn:
            conn.execute(text("TRUNCATE audit_events"))
