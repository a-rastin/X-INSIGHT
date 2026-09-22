"""S24 slice-1 red tests: admin network import/versioning via HTTP (T1).

Assumed contracts (no implementation exists yet; all fail 404 in red phase):
- POST /api/v1/networks {xml: str} as admin (CSRF + Idempotency-Key) -> 201
  {network_id, version_id, version_number=1, sha256, byte_count, xsd_valid}
  with ETag header. sha256 is hex over exact request bytes.
- POST /api/v1/networks/{id}/versions {xml: str} as admin -> 201 with
  version_number=2 and a different sha256; version 1 stays immutable.
- GET /api/v1/networks/{id}/versions lists stored versions (items/versions
  list with per-version sha256); v1 and v2 entries differ.
- GET /api/v1/network-versions/{version_id}/xml returns exact stored bytes
  (byte-identical to the imported document).
- Physician POST/GET on /networks* is 403; anonymous is 401.
- POST with DOCTYPE/entity XML is 422 with a bounded message, no traceback.

All XML fixtures are synthetic two-node documents, never BNs/ as oracle.
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all

XML_V1 = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>Synthetic_Net</NAME>'
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.8 0.2</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.9 0.1 0.3 0.7</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)

# Edited tables (still normalized): new immutable version, different hash.
XML_V2 = (
    b'<BIF VERSION="0.3"><NETWORK><NAME>Synthetic_Net</NAME>'
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<VARIABLE><NAME>B</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.6 0.4</TABLE></DEFINITION>"
    b"<DEFINITION><FOR>B</FOR><GIVEN>A</GIVEN>"
    b"<TABLE>0.7 0.3 0.2 0.8</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)

XML_BAD = (
    b'<!DOCTYPE BIF [<!ENTITY xxe "boom">]>'
    b'<BIF VERSION="0.3"><NETWORK><NAME>XXE_Net</NAME>'
    b"<PROPERTY>&xxe;</PROPERTY>"
    b"<VARIABLE><NAME>A</NAME><OUTCOME>no</OUTCOME><OUTCOME>yes</OUTCOME></VARIABLE>"
    b"<DEFINITION><FOR>A</FOR><TABLE>0.5 0.5</TABLE></DEFINITION>"
    b"</NETWORK></BIF>"
)


@pytest.fixture(autouse=True)
def clean_networks():
    _truncate_all()
    reset_all()
    yield
    reset_all()


def _truncate_all() -> None:
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, audit_events"
            )
        )
        extra = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND "
                    "(tablename LIKE 'network%' OR tablename LIKE 'model%')"
                )
            ).all()
        ]
    for table in extra:
        with db.transaction() as conn:
            if conn.execute(
                text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{table}"}
            ).scalar():
                conn.execute(text(f"TRUNCATE {table}"))


def login(client: TestClient, username="admin", password="admin", role="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200, response.text
    return response.json()


def csrf_headers(client: TestClient, idem: str) -> dict[str, str]:
    return {
        "X-CSRF-Token": client.cookies.get("xinsight_csrf"),
        "Idempotency-Key": idem,
    }


def create_physician(admin: TestClient, username: str):
    response = admin.post(
        "/api/v1/physicians",
        json={"username": username, "password": "synthetic-secret"},
        headers={
            "X-CSRF-Token": admin.cookies.get("xinsight_csrf"),
            "Idempotency-Key": f"s24-{username}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _sha(body: dict) -> str | None:
    for key in ("sha256", "source_sha256"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    nested = body.get("version")
    if isinstance(nested, dict):
        return _sha(nested)
    return None


def _xsd_valid(body: dict) -> bool | None:
    for key in ("xsd_valid", "xsdValid"):
        if isinstance(body.get(key), bool):
            return body[key]
    for key in ("xsd_report", "validation", "xsd"):
        nested = body.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("valid"), bool):
            return nested["valid"]
    return None


def test_admin_imports_synthetic_network_as_immutable_version_1():
    with TestClient(app) as admin:
        login(admin)
        response = admin.post(
            "/api/v1/networks",
            json={"xml": XML_V1.decode()},
            headers=csrf_headers(admin, "s24-import-1"),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body.get("network_id") or body.get("id"), body
        assert body.get("version_id"), body
        assert body.get("version_number", 1) == 1, body
        assert _sha(body) == hashlib.sha256(XML_V1).hexdigest(), body
        assert body.get("byte_count") == len(XML_V1), body
        assert _xsd_valid(body) is True, body
        assert response.headers.get("etag"), response.headers


def test_admin_version_2_preserves_v1_bytes_and_stored_reports_differ():
    with TestClient(app) as admin:
        login(admin)
        created = admin.post(
            "/api/v1/networks",
            json={"xml": XML_V1.decode()},
            headers=csrf_headers(admin, "s24-import-2"),
        )
        assert created.status_code == 201, created.text
        network_id = created.json().get("network_id") or created.json().get("id")
        v1_id = created.json().get("version_id")
        v1_sha = _sha(created.json())
        assert network_id and v1_id and v1_sha

        edited = admin.post(
            f"/api/v1/networks/{network_id}/versions",
            json={"xml": XML_V2.decode()},
            headers=csrf_headers(admin, "s24-edit-1"),
        )
        assert edited.status_code == 201, edited.text
        assert edited.json().get("version_number") == 2, edited.text
        v2_sha = _sha(edited.json())
        assert v2_sha == hashlib.sha256(XML_V2).hexdigest(), edited.text
        assert v2_sha != v1_sha

        exported = admin.get(f"/api/v1/network-versions/{v1_id}/xml")
        assert exported.status_code == 200, exported.text
        assert exported.content == XML_V1

        listed = admin.get(f"/api/v1/networks/{network_id}/versions")
        assert listed.status_code == 200, listed.text
        items = listed.json().get("items", listed.json().get("versions"))
        assert isinstance(items, list) and len(items) == 2, listed.text
        hashes = set()
        for item in items:
            assert isinstance(item, dict), item
            digest = item.get("sha256") or item.get("source_sha256")
            assert digest, item
            hashes.add(digest)
        assert hashes == {v1_sha, v2_sha}, listed.text


def test_physician_denied_and_anonymous_unauthenticated():
    with TestClient(app) as admin, TestClient(app) as physician, TestClient(
        app
    ) as anon:
        login(admin)
        created = admin.post(
            "/api/v1/networks",
            json={"xml": XML_V1.decode()},
            headers=csrf_headers(admin, "s24-import-3"),
        )
        assert created.status_code == 201, created.text
        network_id = created.json().get("network_id") or created.json().get("id")

        create_physician(admin, "drnetworks")
        login(physician, "drnetworks", "synthetic-secret", "physician")
        physician_headers = {"X-CSRF-Token": physician.cookies.get("xinsight_csrf")}
        assert (
            physician.post(
                "/api/v1/networks",
                json={"xml": XML_V1.decode()},
                headers={**physician_headers, "Idempotency-Key": "s24-phys-1"},
            ).status_code
            == 403
        )
        assert physician.get("/api/v1/networks").status_code == 403
        assert (
            physician.get(f"/api/v1/networks/{network_id}/versions").status_code
            == 403
        )

        assert anon.post("/api/v1/networks", json={"xml": "x"}).status_code == 401
        assert anon.get("/api/v1/networks").status_code == 401


def test_invalid_xml_rejected_with_bounded_message_and_no_traceback():
    with TestClient(app) as admin:
        login(admin)
        response = admin.post(
            "/api/v1/networks",
            json={"xml": XML_BAD.decode()},
            headers=csrf_headers(admin, "s24-bad-1"),
        )
        assert response.status_code == 422, response.text
        assert "traceback" not in response.text.lower()
        assert len(response.text) < 5000, len(response.text)


# --- S24 slice-2 red tests: read-only graph + validate reports (T-seam) ---
#
# Assumed contracts (no implementation exists yet; graph/validate fail 404):
# - GET /api/v1/network-versions/{id}/graph as admin -> 200
#   {nodes == ["A","B"], edges == [["A","B"]],
#    states == {"A": ["no","yes"], "B": ["no","yes"]} in XML order}
#   plus validation status (xsd_valid / semantic executable / admission
#   admitted).
# - GET graph as physician 403, anon 401.
# - No graphical edit: PUT/PATCH/POST on .../graph is 404/405, never 200.
# - POST /api/v1/network-versions/{id}/validate as admin -> 200 with
#   separate reports (at minimum xsd_report, semantic_report,
#   admission_report keys) without mutating stored bytes/hash.
#
# Synthetic 2-node fixtures only (XML_V1 reuse).


def _semantic_executable(body: dict) -> bool | None:
    for key in ("semantic_report", "semantic", "semantics"):
        nested = body.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("executable"), bool):
            return nested["executable"]
    if isinstance(body.get("executable"), bool):
        return body["executable"]
    return None


def _admission_admitted(body: dict) -> bool | None:
    for key in ("admission_report", "admission", "admission_decision"):
        nested = body.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("admitted"), bool):
            return nested["admitted"]
    if isinstance(body.get("admitted"), bool):
        return body["admitted"]
    return None


def _import_v1(admin: TestClient, idem: str) -> dict:
    created = admin.post(
        "/api/v1/networks",
        json={"xml": XML_V1.decode()},
        headers=csrf_headers(admin, idem),
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_admin_graph_returns_ordered_nodes_edges_states_and_validation():
    with TestClient(app) as admin:
        login(admin)
        created = _import_v1(admin, "s24-graph-1")
        version_id = created.get("version_id")
        assert version_id, created

        response = admin.get(f"/api/v1/network-versions/{version_id}/graph")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("nodes") == ["A", "B"], body
        assert body.get("edges") == [["A", "B"]], body
        assert body.get("states") == {"A": ["no", "yes"], "B": ["no", "yes"]}, body
        assert _xsd_valid(body) is True, body
        assert _semantic_executable(body) is True, body
        assert _admission_admitted(body) is True, body


def test_graph_denied_for_physician_and_anonymous():
    with TestClient(app) as admin, TestClient(app) as physician, TestClient(
        app
    ) as anon:
        login(admin)
        created = _import_v1(admin, "s24-graph-2")
        version_id = created.get("version_id")
        assert version_id, created

        create_physician(admin, "drgraph")
        login(physician, "drgraph", "synthetic-secret", "physician")
        assert (
            physician.get(f"/api/v1/network-versions/{version_id}/graph").status_code
            == 403
        )
        assert anon.get(f"/api/v1/network-versions/{version_id}/graph").status_code == 401


def test_graph_has_no_edit_operation():
    with TestClient(app) as admin:
        login(admin)
        created = _import_v1(admin, "s24-graph-3")
        version_id = created.get("version_id")
        assert version_id, created
        target = f"/api/v1/network-versions/{version_id}/graph"
        headers = csrf_headers(admin, "s24-graph-noedit-1")
        for method in ("put", "patch", "post"):
            response = getattr(admin, method)(target, json={}, headers=headers)
            assert response.status_code in (404, 405), response.text
            assert response.status_code != 200, response.text


def test_validate_returns_separate_reports_without_mutation():
    with TestClient(app) as admin:
        login(admin)
        created = _import_v1(admin, "s24-validate-1")
        version_id = created.get("version_id")
        assert version_id, created
        expected_sha = _sha(created)
        assert expected_sha == hashlib.sha256(XML_V1).hexdigest(), created

        before = admin.get(f"/api/v1/network-versions/{version_id}/xml")
        assert before.status_code == 200, before.text
        assert before.content == XML_V1

        response = admin.post(
            f"/api/v1/network-versions/{version_id}/validate",
            headers=csrf_headers(admin, "s24-validate-2"),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        for key in ("xsd_report", "semantic_report", "admission_report"):
            assert isinstance(body.get(key), dict), body

        after = admin.get(f"/api/v1/network-versions/{version_id}/xml")
        assert after.status_code == 200, after.text
        assert after.content == XML_V1
        listed = admin.get(
            f"/api/v1/networks/{created.get('network_id') or created.get('id')}/versions"
        )
        assert listed.status_code == 200, listed.text
        items = listed.json().get("items", listed.json().get("versions"))
        assert isinstance(items, list) and len(items) == 1, listed.text
        assert (items[0].get("sha256") or items[0].get("source_sha256")) == expected_sha


# --- S24 slice-3 red tests: bundle activate/rollback (T1 pointer + T5) ---
#
# Assumed contracts (no implementation exists yet; activate/rollback/pointer
# fail 404 in the red phase):
# - Read path: GET /api/v1/model-bundles/{workflow} returns the current
#   pointer {workflow, revision, bundle_hash, pins}. This read discovers
#   expected_revision (0 when no pointer exists yet). No alternative read
#   path is used by these tests.
# - POST /api/v1/model-bundles/activate as admin with
#   {workflow: "registration",
#    pins: [{question_key, network_version_id,
#            review: {decision: "approved", reviewer, date}} x7
#           in REGISTRATION_ORDER],
#    expected_revision: <current pointer revision, 0 when none>}
#   -> 200 {workflow, revision (incremented), bundle_hash, pins}.
# - Incomplete bundle (6/7 pins, one key missing) -> 422 with a
#   missing_question error; pointer revision unchanged.
# - Unreviewed bundle (one pin review decision != "approved" or missing)
#   -> 422 with an unreviewed_package error; pointer unchanged.
# - POST /api/v1/model-bundles/rollback as admin with
#   {workflow, target_revision, expected_revision} (target_bundle_hash is an
#   accepted alternative selector) selects prior valid versions as a NEW
#   activation event: revision increments again, bundle_hash/pins match the
#   targeted revision, and audit history is preserved (not truncated).
# - Stale expected_revision on activate/rollback -> 412, no mutation.
# - Physician POST activate/rollback is 403; anonymous is 401.
#
# All fixtures are synthetic two-node documents (XML_V1 reuse); question_key
# distinguishes pins, never BNs/ as oracle. Truncate guards are inherited
# from the module clean_networks fixture (model%/network% tables).
# Run-pinning of existing runs (plan 7.3 "existing runs retain pinned
# versions") has no runs yet and is out of scope for these tests.

REGISTRATION_ORDER_SYNTHETIC = [
    "hospitalization",
    "pharmacotherapy",
    "involuntary_care",
    "high_suicide_clozapine",
    "lai_indication_choice",
    "aggression_clozapine",
    "established_case_clozapine",
]

REVIEW_APPROVED = {"decision": "approved", "reviewer": "owner", "date": "2026-09-22"}


def _import_synthetic_versions(admin: TestClient, prefix: str, count: int) -> list[str]:
    version_ids: list[str] = []
    for index in range(count):
        created = admin.post(
            "/api/v1/networks",
            json={"xml": XML_V1.decode()},
            headers=csrf_headers(admin, f"{prefix}-{index}"),
        )
        assert created.status_code == 201, created.text
        version_id = created.json().get("version_id")
        assert version_id, created.text
        version_ids.append(version_id)
    return version_ids


def _build_pins(
    version_ids: list[str],
    review: dict | None = None,
    review_override_index: int | None = None,
    review_override: dict | None = None,
) -> list[dict]:
    assert len(version_ids) == len(REGISTRATION_ORDER_SYNTHETIC)
    pins: list[dict] = []
    for position, (key, version_id) in enumerate(
        zip(REGISTRATION_ORDER_SYNTHETIC, version_ids)
    ):
        entry_review = dict(review if review is not None else REVIEW_APPROVED)
        if review_override_index is not None and position == review_override_index:
            assert review_override is not None
            entry_review = dict(review_override)
        pins.append(
            {
                "question_key": key,
                "network_version_id": version_id,
                "review": entry_review,
            }
        )
    return pins


def _pointer_revision_or_zero(
    admin: TestClient,
    workflow: str,
) -> tuple[int, dict | None]:
    response = admin.get(f"/api/v1/model-bundles/{workflow}")
    if response.status_code == 404:
        return 0, None
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("workflow") == workflow, body
    return int(body.get("revision", 0)), body


def test_activate_complete_registration_bundle_increments_revision():
    with TestClient(app) as admin:
        login(admin)
        version_ids = _import_synthetic_versions(admin, "s24-bundle-act", 7)
        expected, _ = _pointer_revision_or_zero(admin, "registration")
        assert expected == 0

        response = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": _build_pins(version_ids),
                "expected_revision": expected,
            },
            headers=csrf_headers(admin, "s24-bundle-act-1"),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("workflow") == "registration", body
        assert body.get("revision") == expected + 1, body
        assert body.get("bundle_hash"), body
        pins = body.get("pins")
        assert isinstance(pins, list) and len(pins) == 7, body
        keys = [p.get("question_key") for p in pins]
        assert keys == REGISTRATION_ORDER_SYNTHETIC, body

        stale = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": _build_pins(version_ids),
                "expected_revision": expected,
            },
            headers=csrf_headers(admin, "s24-bundle-act-stale"),
        )
        assert stale.status_code == 412, stale.text


def test_activate_incomplete_bundle_rejected_pointer_unchanged():
    with TestClient(app) as admin:
        login(admin)
        version_ids = _import_synthetic_versions(admin, "s24-bundle-miss", 7)
        expected, _ = _pointer_revision_or_zero(admin, "registration")

        pins = _build_pins(version_ids)[:6]
        assert len(pins) == 6
        response = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": pins,
                "expected_revision": expected,
            },
            headers=csrf_headers(admin, "s24-bundle-miss-1"),
        )
        assert response.status_code == 422, response.text
        assert "missing_question" in response.text, response.text

        after, _ = _pointer_revision_or_zero(admin, "registration")
        assert after == expected


def test_activate_unreviewed_bundle_rejected_pointer_unchanged():
    with TestClient(app) as admin:
        login(admin)
        version_ids = _import_synthetic_versions(admin, "s24-bundle-unrev", 7)
        expected, _ = _pointer_revision_or_zero(admin, "registration")

        pins = _build_pins(
            version_ids,
            review_override_index=3,
            review_override={
                "decision": "pending",
                "reviewer": "owner",
                "date": "2026-09-22",
            },
        )
        response = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": pins,
                "expected_revision": expected,
            },
            headers=csrf_headers(admin, "s24-bundle-unrev-1"),
        )
        assert response.status_code == 422, response.text
        assert "unreviewed_package" in response.text, response.text

        after, _ = _pointer_revision_or_zero(admin, "registration")
        assert after == expected


def test_rollback_to_prior_revision_creates_new_activation_and_preserves_audit():
    with TestClient(app) as admin:
        login(admin)
        first_ids = _import_synthetic_versions(admin, "s24-bundle-rb-a", 7)
        first = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": _build_pins(first_ids),
                "expected_revision": 0,
            },
            headers=csrf_headers(admin, "s24-bundle-rb-1"),
        )
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body.get("revision") == 1, first_body
        first_hash = first_body.get("bundle_hash")
        assert first_hash, first_body

        second_ids = _import_synthetic_versions(admin, "s24-bundle-rb-b", 7)
        second = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": _build_pins(second_ids),
                "expected_revision": 1,
            },
            headers=csrf_headers(admin, "s24-bundle-rb-2"),
        )
        assert second.status_code == 200, second.text
        assert second.json().get("revision") == 2, second.text

        rolled = admin.post(
            "/api/v1/model-bundles/rollback",
            json={
                "workflow": "registration",
                "target_revision": 1,
                "expected_revision": 2,
            },
            headers=csrf_headers(admin, "s24-bundle-rb-3"),
        )
        assert rolled.status_code == 200, rolled.text
        rolled_body = rolled.json()
        assert rolled_body.get("workflow") == "registration", rolled_body
        assert rolled_body.get("revision") == 3, rolled_body
        assert rolled_body.get("bundle_hash") == first_hash, rolled_body

        pointer = admin.get("/api/v1/model-bundles/registration")
        assert pointer.status_code == 200, pointer.text
        pointer_body = pointer.json()
        assert pointer_body.get("revision") == 3, pointer_body
        assert pointer_body.get("bundle_hash") == first_hash, pointer_body

        stale_rb = admin.post(
            "/api/v1/model-bundles/rollback",
            json={
                "workflow": "registration",
                "target_revision": 1,
                "expected_revision": 2,
            },
            headers=csrf_headers(admin, "s24-bundle-rb-stale"),
        )
        assert stale_rb.status_code == 412, stale_rb.text

        audit = admin.get("/api/v1/audit-events", params={"limit": 100})
        assert audit.status_code == 200, audit.text
        items = audit.json().get("items", [])
        assert isinstance(items, list), audit.text
        matches = [
            event
            for event in items
            if isinstance(event, dict) and "registration" in str(event).lower()
        ]
        assert len(matches) >= 3, audit.text


def test_bundle_activate_rollback_denied_for_physician_and_anonymous():
    with (
        TestClient(app) as admin,
        TestClient(app) as physician,
        TestClient(app) as anon,
    ):
        login(admin)
        version_ids = _import_synthetic_versions(admin, "s24-bundle-auth", 7)
        payload = {
            "workflow": "registration",
            "pins": _build_pins(version_ids),
            "expected_revision": 0,
        }
        rollback_payload = {
            "workflow": "registration",
            "target_revision": 1,
            "expected_revision": 1,
        }

        create_physician(admin, "drbundles")
        login(physician, "drbundles", "synthetic-secret", "physician")
        physician_headers = {"X-CSRF-Token": physician.cookies.get("xinsight_csrf")}
        assert (
            physician.post(
                "/api/v1/model-bundles/activate",
                json=payload,
                headers={**physician_headers, "Idempotency-Key": "s24-bundle-phys-1"},
            ).status_code
            == 403
        )
        assert (
            physician.post(
                "/api/v1/model-bundles/rollback",
                json=rollback_payload,
                headers={**physician_headers, "Idempotency-Key": "s24-bundle-phys-2"},
            ).status_code
            == 403
        )

        activate_anon = anon.post("/api/v1/model-bundles/activate", json=payload)
        assert activate_anon.status_code == 401
        rollback_anon = anon.post(
            "/api/v1/model-bundles/rollback", json=rollback_payload
        )
        assert rollback_anon.status_code == 401


def test_get_current_bundle_pointer_returns_revision_hash_and_pins():
    with TestClient(app) as admin:
        login(admin)
        version_ids = _import_synthetic_versions(admin, "s24-bundle-ptr", 7)
        activated = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": _build_pins(version_ids),
                "expected_revision": 0,
            },
            headers=csrf_headers(admin, "s24-bundle-ptr-1"),
        )
        assert activated.status_code == 200, activated.text
        activated_body = activated.json()

        pointer = admin.get("/api/v1/model-bundles/registration")
        assert pointer.status_code == 200, pointer.text
        body = pointer.json()
        assert body.get("workflow") == "registration", body
        assert body.get("revision") == activated_body.get("revision") == 1, body
        assert body.get("bundle_hash") == activated_body.get("bundle_hash"), body
        pins = body.get("pins")
        assert isinstance(pins, list) and len(pins) == 7, body
        keys = [p.get("question_key") for p in pins]
        assert keys == REGISTRATION_ORDER_SYNTHETIC, body


# --- S24 slice-4 red tests: re-pin one question to v2, stale guard, empty pointer ---
#
# Assumed contracts (no slice-4 implementation yet; re-pin/stale-detail and
# empty-pointer reads fail before the slice lands):
# - After activating a registration bundle pinning v1 of a network, POST
#   /api/v1/networks/{id}/versions with slightly edited valid synthetic XML
#   (TABLE values changed, still normalized) -> 201 version_number 2 with a
#   different sha256; then POST /api/v1/model-bundles/activate pinning v2 for
#   that question_key (expected_revision = prior revision) -> 200 revision+1.
# - GET /api/v1/networks/{id}/versions then lists both v1+v2 with validation
#   details (each entry carries sha256/byte_count plus xsd_valid or a report
#   dict); GET /api/v1/network-versions/{v1_id}/xml stays byte-identical to
#   the original v1 bytes; GET v1 graph + POST v1 validate still return 200.
# - Stale activate (outdated expected_revision, e.g. 1 when current is 2)
#   -> 412 with STALE_REVISION code and no pointer change (GET still rev 2).
# - Fresh truncate (module fixture) with no activation yet:
#   GET /api/v1/model-bundles/registration -> 200 revision 0, null hash.
#
# Synthetic two-node documents only (XML_V1/XML_V2 reuse); never BNs/.


def _import_seven_with_ids(
    admin: TestClient, prefix: str
) -> tuple[list[str], list[str]]:
    network_ids: list[str] = []
    version_ids: list[str] = []
    for index in range(7):
        created = admin.post(
            "/api/v1/networks",
            json={"xml": XML_V1.decode()},
            headers=csrf_headers(admin, f"{prefix}-{index}"),
        )
        assert created.status_code == 201, created.text
        body = created.json()
        network_id = body.get("network_id") or body.get("id")
        version_id = body.get("version_id")
        assert network_id and version_id, body
        network_ids.append(network_id)
        version_ids.append(version_id)
    return network_ids, version_ids


def test_repin_one_question_to_v2_preserves_v1_immutability():
    with TestClient(app) as admin:
        login(admin)
        network_ids, version_ids = _import_seven_with_ids(admin, "s24-repin-imp")
        first_network_id = network_ids[0]
        v1_id = version_ids[0]
        v1_sha = hashlib.sha256(XML_V1).hexdigest()

        first = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": _build_pins(version_ids),
                "expected_revision": 0,
            },
            headers=csrf_headers(admin, "s24-repin-act-1"),
        )
        assert first.status_code == 200, first.text
        assert first.json().get("revision") == 1, first.text

        edited = admin.post(
            f"/api/v1/networks/{first_network_id}/versions",
            json={"xml": XML_V2.decode()},
            headers=csrf_headers(admin, "s24-repin-ver-2"),
        )
        assert edited.status_code == 201, edited.text
        assert edited.json().get("version_number") == 2, edited.text
        v2_id = edited.json().get("version_id")
        v2_sha = _sha(edited.json())
        assert v2_id, edited.text
        assert v2_sha == hashlib.sha256(XML_V2).hexdigest(), edited.text
        assert v2_sha != v1_sha

        repinned_ids = [v2_id, *version_ids[1:]]
        repinned = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": _build_pins(repinned_ids),
                "expected_revision": 1,
            },
            headers=csrf_headers(admin, "s24-repin-act-2"),
        )
        assert repinned.status_code == 200, repinned.text
        assert repinned.json().get("revision") == 2, repinned.text

        listed = admin.get(f"/api/v1/networks/{first_network_id}/versions")
        assert listed.status_code == 200, listed.text
        items = listed.json().get("items", listed.json().get("versions"))
        assert isinstance(items, list) and len(items) == 2, listed.text
        by_number = {}
        hashes = set()
        for item in items:
            assert isinstance(item, dict), item
            digest = item.get("sha256") or item.get("source_sha256")
            assert digest, item
            hashes.add(digest)
            assert isinstance(item.get("byte_count"), int), item
            has_flag = isinstance(item.get("xsd_valid"), bool)
            has_report = any(
                isinstance(item.get(k), dict)
                for k in ("xsd_report", "validation", "xsd", "semantic_report",
                          "admission_report")
            )
            assert has_flag or has_report, item
            by_number[item.get("version_number", item.get("version"))] = item
        assert hashes == {v1_sha, v2_sha}, listed.text
        assert set(by_number) == {1, 2}, listed.text

        exported = admin.get(f"/api/v1/network-versions/{v1_id}/xml")
        assert exported.status_code == 200, exported.text
        assert exported.content == XML_V1

        graph = admin.get(f"/api/v1/network-versions/{v1_id}/graph")
        assert graph.status_code == 200, graph.text

        validated = admin.post(
            f"/api/v1/network-versions/{v1_id}/validate",
            headers=csrf_headers(admin, "s24-repin-validate-1"),
        )
        assert validated.status_code == 200, validated.text
        for key in ("xsd_report", "semantic_report", "admission_report"):
            assert isinstance(validated.json().get(key), dict), validated.text


def test_stale_activate_after_repin_rejected_pointer_unchanged():
    with TestClient(app) as admin:
        login(admin)
        network_ids, version_ids = _import_seven_with_ids(admin, "s24-repin-stale")
        first_network_id = network_ids[0]

        first = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": _build_pins(version_ids),
                "expected_revision": 0,
            },
            headers=csrf_headers(admin, "s24-repin-stale-1"),
        )
        assert first.status_code == 200, first.text

        edited = admin.post(
            f"/api/v1/networks/{first_network_id}/versions",
            json={"xml": XML_V2.decode()},
            headers=csrf_headers(admin, "s24-repin-stale-2"),
        )
        assert edited.status_code == 201, edited.text
        v2_id = edited.json().get("version_id")
        assert v2_id, edited.text

        repinned = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": _build_pins([v2_id, *version_ids[1:]]),
                "expected_revision": 1,
            },
            headers=csrf_headers(admin, "s24-repin-stale-3"),
        )
        assert repinned.status_code == 200, repinned.text
        assert repinned.json().get("revision") == 2, repinned.text

        stale = admin.post(
            "/api/v1/model-bundles/activate",
            json={
                "workflow": "registration",
                "pins": _build_pins([v2_id, *version_ids[1:]]),
                "expected_revision": 1,
            },
            headers=csrf_headers(admin, "s24-repin-stale-4"),
        )
        assert stale.status_code == 412, stale.text
        assert "STALE_REVISION" in stale.text, stale.text

        pointer = admin.get("/api/v1/model-bundles/registration")
        assert pointer.status_code == 200, pointer.text
        assert pointer.json().get("revision") == 2, pointer.text


def test_empty_registration_pointer_is_revision_zero_null_hash():
    with TestClient(app) as admin:
        login(admin)
        pointer = admin.get("/api/v1/model-bundles/registration")
        assert pointer.status_code == 200, pointer.text
        body = pointer.json()
        assert body.get("workflow") == "registration", body
        assert body.get("revision") == 0, body
        assert body.get("bundle_hash") is None, body
