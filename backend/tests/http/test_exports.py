"""S53 slices 1-2 (+ report/audit red coverage): CSV exports + printable report.

Scope: docs/dev/plan.md 10.1, docs/dev/tasks.md S53 items 1-3 (+ audit hook);
seam T1 only (authenticated HTTP against real PostgreSQL, plus the existing
GET /api/v1/audit-events read seam for assertions). SYNTHETIC VALUES ONLY.

Behavior under test (NONE implemented -- RED, expect 404s on the export and
report routes):
- Admin GET /api/v1/exports/patients.csv -> 200 text/csv; charset=utf-8,
  stable English headers incl. patient_id, no credential columns; physician
  403; anonymous 401.
- Patient ID ``0012345678`` survives as exact bytes (no zero-stripping, no
  ``="..."`` formula wrapper; import the column as text in spreadsheets --
  CSV carries no type information).
- Formula-like free text (phone field, the free-text vehicle: patient names
  are letters-only per validation) is neutralized with a leading ``'``
  (or space/tab) prefix; quotes/newlines round-trip via CSV quoting.
- Admin GET /api/v1/exports/physicians.csv -> 200 with stable headers and
  no credentials; physician 403; anonymous 401.
- GET /api/v1/patients/{id}/report (printable HTML) for admin and author
  physician: 200 text/html, user/note text escaped, draft/signed/current/
  historical labels plus research notice, Cache-Control: private, no-store.
- Each list export appends an audit event visible via GET
  /api/v1/audit-events (operation containing "export").
"""

import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_exports():
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


def admin_headers(client, key):
    return {
        "X-CSRF-Token": client.cookies.get("xinsight_csrf"),
        "Idempotency-Key": key,
    }


def create_physician(admin, username, key):
    created = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "secret"},
        headers=admin_headers(admin, key),
    )
    assert created.status_code == 201
    return created.json()


def create_patient(physician, patient_id, key, **overrides):
    body = {
        "first_name": "Anna",
        "last_name": "Muller",
        "sex": "F",
        "age": 30,
        "patient_id": patient_id,
        "clinical_status": "first_time",
        **overrides,
    }
    response = physician.post(
        "/api/v1/patients", json=body, headers=admin_headers(physician, key)
    )
    assert response.status_code == 201
    return response.json()


def csv_rows(response):
    return list(csv.DictReader(io.StringIO(response.text)))


def assert_no_credential_columns(headers):
    forbidden = ("password", "hash", "secret", "credential", "token", "key")
    for header in headers:
        lowered = header.lower()
        for marker in forbidden:
            assert marker not in lowered, f"credential-like column {header!r}"


def test_admin_patients_csv_headers_and_access():
    """S53 item 1 (RED): admin patients CSV headers/permissions (T1)."""
    with (
        TestClient(app) as admin,
        TestClient(app) as physician,
        TestClient(app) as anon,
    ):
        login(admin)
        create_physician(admin, "exportdoc", "s53-exp-create")
        login(physician, "exportdoc", "secret", "physician")
        create_patient(physician, "0012345678", "s53-exp-patient")

        assert anon.get("/api/v1/exports/patients.csv").status_code == 401
        assert physician.get("/api/v1/exports/patients.csv").status_code == 403

        first = admin.get("/api/v1/exports/patients.csv")
        assert first.status_code == 200
        content_type = first.headers.get("content-type", "").lower()
        assert "text/csv" in content_type
        assert "charset=utf-8" in content_type

        reader = csv.DictReader(io.StringIO(first.text))
        headers = reader.fieldnames
        assert headers, "CSV must carry a header row"
        assert all(h == h.strip() and h for h in headers)
        assert all(h.isascii() for h in headers)
        assert "patient_id" in headers
        assert_no_credential_columns(headers)

        second = admin.get("/api/v1/exports/patients.csv")
        assert second.status_code == 200
        assert csv.DictReader(io.StringIO(second.text)).fieldnames == headers


def test_patients_csv_preserves_patient_id_bytes():
    """S53 item 1 (RED): ID 0012345678 stays exact bytes, no formula wrap."""
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "iddoc", "s53-id-create")
        login(physician, "iddoc", "secret", "physician")
        create_patient(physician, "0012345678", "s53-id-patient")

        response = admin.get("/api/v1/exports/patients.csv")
        assert response.status_code == 200
        raw = response.content
        assert b"0012345678" in raw
        assert b'="0012345678"' not in raw
        assert b'="0012345678' not in raw

        rows = csv_rows(response)
        by_id = {row["patient_id"]: row for row in rows}
        assert by_id["0012345678"]["patient_id"] == "0012345678"


def test_patients_csv_neutralizes_formulas_and_quotes():
    """S53 item 2 (RED): formula prefixing + quote/newline round-trip (T1).

    Free-text vehicle is the optional phone field (patient names are
    letters-only per validation, so names cannot carry ``=``/``@``).
    """
    payloads = [
        ("0020000001", "=cmd|'/c calc'!A0"),
        ("0020000002", "+1+1"),
        ("0020000003", "-2+3"),
        ("0020000004", "@SUM(A1:A2)"),
    ]
    quoted_id = "0020000005"
    quoted_phone = 'say "hi", ok\nnew line'
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "formuladoc", "s53-form-create")
        login(physician, "formuladoc", "secret", "physician")
        for i, (pid, phone) in enumerate(payloads):
            create_patient(physician, pid, f"s53-form-{i}", phone=phone)
        create_patient(physician, quoted_id, "s53-form-q", phone=quoted_phone)

        response = admin.get("/api/v1/exports/patients.csv")
        assert response.status_code == 200
        rows = csv_rows(response)
        by_id = {row["patient_id"]: row for row in rows}

        for pid, payload in payloads:
            cell = by_id[pid]["phone"]
            assert cell != payload, f"formula payload served raw for {pid}"
            assert cell.endswith(payload), f"neutralized cell must keep {payload!r}"
            assert cell[0] in ("'", " ", "\t"), f"missing neutralization prefix: {cell!r}"

        assert by_id[quoted_id]["phone"] == quoted_phone


def test_admin_physicians_csv_headers_and_access():
    """S53 item 1 (RED): admin physicians CSV headers/permissions (T1)."""
    with (
        TestClient(app) as admin,
        TestClient(app) as physician,
        TestClient(app) as anon,
    ):
        login(admin)
        created = create_physician(admin, "csvdoc", "s53-phys-create")
        login(physician, "csvdoc", "secret", "physician")

        assert anon.get("/api/v1/exports/physicians.csv").status_code == 401
        assert physician.get("/api/v1/exports/physicians.csv").status_code == 403

        first = admin.get("/api/v1/exports/physicians.csv")
        assert first.status_code == 200
        content_type = first.headers.get("content-type", "").lower()
        assert "text/csv" in content_type
        assert "charset=utf-8" in content_type

        reader = csv.DictReader(io.StringIO(first.text))
        headers = reader.fieldnames
        assert headers, "CSV must carry a header row"
        assert "username" in headers
        assert_no_credential_columns(headers)
        assert created["username"] in first.text

        second = admin.get("/api/v1/exports/physicians.csv")
        assert second.status_code == 200
        assert csv.DictReader(io.StringIO(second.text)).fieldnames == headers


def test_patient_report_html_escaped_labels_and_cache():
    """S53 item 3 (RED): printable report escaping/labels/cache (T1).

    ``<script>`` payloads ride the free-text note plus a direct-SQL name
    injection (setup only: names are letters-only via the API, the report
    must still escape whatever is stored).
    """
    xss_note = "<script>alert('note-xss')</script>"
    xss_name = "Evil<script>alert('name-xss')</script>"
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "reportdoc", "s53-rep-create")
        login(physician, "reportdoc", "secret", "physician")
        made = create_patient(physician, "0030000001", "s53-rep-patient")
        patient_uuid = made["patient"]["id"]
        encounter_id = made["encounter"]["id"]

        noted = physician.post(
            f"/api/v1/encounters/{encounter_id}/notes",
            json={"page": "history", "text": xss_note},
            headers={"X-CSRF-Token": physician.cookies.get("xinsight_csrf")},
        )
        assert noted.status_code == 201
        with db.transaction() as conn:
            conn.execute(
                text("UPDATE patients SET first_name = :name WHERE id = :id"),
                {"name": xss_name, "id": patient_uuid},
            )

        for viewer in (admin, physician):
            response = viewer.get(f"/api/v1/patients/{patient_uuid}/report")
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "").lower()
            cache = response.headers.get("cache-control", "").lower()
            assert "private" in cache
            assert "no-store" in cache
            body = response.text
            assert "&lt;script&gt;" in body
            assert "<script" not in body.lower()
            lowered = body.lower()
            for label in ("draft", "signed", "current", "historical", "research"):
                assert label in lowered, f"missing report label {label!r}"


def test_export_emits_audit_event():
    """S53 verify (RED): list export appends an export audit event (T1)."""
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        create_physician(admin, "auditdoc", "s53-audit-create")
        login(physician, "auditdoc", "secret", "physician")
        create_patient(physician, "0040000001", "s53-audit-patient")

        response = admin.get("/api/v1/exports/patients.csv")
        assert response.status_code == 200

        listed = admin.get("/api/v1/audit-events", params={"limit": 100})
        assert listed.status_code == 200
        assert any(
            "export" in str(item.get("operation", "")).lower()
            for item in listed.json()["items"]
        )
