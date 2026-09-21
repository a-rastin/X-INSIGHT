"""S04 physician administration through T1 HTTP and disposable PostgreSQL."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from x_insight import db
from x_insight.app import app
from x_insight.identity.throttle import reset_all


@pytest.fixture(autouse=True)
def clean_accounts():
    with db.transaction() as conn:
        conn.execute(
            text(
                "TRUNCATE encounter_notes, sessions, users, "
                "patients, encounters, audit_events"
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


def headers(client, key, etag=None):
    result = {
        "X-CSRF-Token": client.cookies.get("xinsight_csrf"),
        "Idempotency-Key": key,
    }
    if etag is not None:
        result["If-Match"] = etag
    return result


def test_admin_manages_safe_physician_accounts_with_stable_identity():
    with TestClient(app) as admin, TestClient(app) as physician:
        assert (
            physician.post(
                "/api/v1/physicians", json={"username": "anonymous", "password": "x"}
            ).status_code
            == 401
        )
        login(admin)
        assert (
            admin.post(
                "/api/v1/physicians",
                json={"username": "extra-admin", "password": "x", "role": "admin"},
                headers=headers(admin, "create-admin"),
            ).status_code
            == 422
        )
        created = admin.post(
            "/api/v1/physicians",
            json={"username": " Doctor ", "password": "synthetic-secret"},
            headers=headers(admin, "create-doctor"),
        )
        assert created.status_code == 201
        account = created.json()
        assert set(account) == {
            "id",
            "username",
            "role",
            "active",
            "revision",
            "schema_version",
        }
        assert account["username"] == "doctor"
        assert account["role"] == "physician"
        assert account["active"] is True
        path = f"/api/v1/physicians/{account['id']}"
        found = admin.get(path)
        assert found.status_code == 200
        assert found.json() == account
        listing = admin.get("/api/v1/physicians").json()
        assert listing["items"] == [account]
        assert listing["next_cursor"] is None
        assert "schema_version" in listing
        login(physician, "doctor", "synthetic-secret", "physician")
        assert physician.get("/api/v1/me").json()["id"] == account["id"]
        for response in (
            physician.get("/api/v1/physicians"),
            physician.get(path),
            physician.post(
                "/api/v1/physicians",
                json={"username": "intruder", "password": "x"},
                headers=headers(physician, "unauthorized-create"),
            ),
            physician.patch(
                path,
                json={"username": "intruder"},
                headers=headers(physician, "unauthorized-edit", found.headers["etag"]),
            ),
        ):
            assert response.status_code == 403
        assert (
            admin.patch(
                path,
                json={"username": "renamed"},
                headers={
                    "If-Match": found.headers["etag"],
                    "Idempotency-Key": "no-csrf",
                },
            ).status_code
            == 403
        )
        assert (
            admin.patch(
                path,
                json={"role": "admin"},
                headers=headers(admin, "elevate", found.headers["etag"]),
            ).status_code
            == 422
        )
        renamed = admin.patch(
            path,
            json={"username": "renamed"},
            headers=headers(admin, "rename", found.headers["etag"]),
        )
        assert renamed.status_code == 200
        assert renamed.json()["id"] == account["id"]
        assert renamed.json()["username"] == "renamed"
        assert admin.get(path).json() == renamed.json()
        assert physician.get("/api/v1/me").status_code == 401
        login(physician, "renamed", "synthetic-secret", "physician")
        assert physician.get("/api/v1/me").json()["id"] == account["id"]


def test_password_reset_revokes_all_sessions_and_obeys_account_revision():
    with TestClient(app) as admin, TestClient(app) as first, TestClient(app) as second:
        login(admin)
        created = admin.post(
            "/api/v1/physicians",
            json={"username": "doctor", "password": "old-secret"},
            headers=headers(admin, "create-reset"),
        )
        assert created.status_code == 201
        path = f"/api/v1/physicians/{created.json()['id']}"
        original_etag = created.headers["etag"]
        login(first, "doctor", "old-secret", "physician")
        login(second, "doctor", "old-secret", "physician")
        reset = admin.patch(
            path,
            json={"password": "new-secret"},
            headers=headers(admin, "reset", original_etag),
        )
        assert reset.status_code == 200
        assert reset.headers["etag"] != original_etag
        assert reset.json()["id"] == created.json()["id"]
        assert first.get("/api/v1/me").status_code == 401
        assert second.get("/api/v1/me").status_code == 401
        assert (
            first.post(
                "/api/v1/auth/login",
                json={
                    "username": "doctor",
                    "password": "old-secret",
                    "role": "physician",
                },
            ).status_code
            == 401
        )
        login(first, "doctor", "new-secret", "physician")
        for etag in (None, original_etag):
            assert (
                admin.patch(
                    path,
                    json={"password": "stale-secret"},
                    headers=headers(admin, f"stale-{etag}", etag),
                ).status_code
                == 412
            )
        for password in ("", None):
            assert (
                admin.patch(
                    path,
                    json={"password": password},
                    headers=headers(admin, "invalid-password", reset.headers["etag"]),
                ).status_code
                == 422
            )
        assert admin.get(path).headers["etag"] == reset.headers["etag"]
        changed = first.post(
            "/api/v1/me/password",
            json={"current_password": "new-secret", "new_password": "self-secret"},
            headers=headers(first, "self-password"),
        )
        assert changed.status_code == 200
        assert admin.get(path).headers["etag"] != reset.headers["etag"]
        assert (
            admin.patch(
                path,
                json={"password": "overwrite-self-secret"},
                headers=headers(
                    admin, "stale-after-self-change", reset.headers["etag"]
                ),
            ).status_code
            == 412
        )
        login(second, "doctor", "self-secret", "physician")


def test_deactivation_requires_review_and_explicit_discard_confirmation():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        created = admin.post(
            "/api/v1/physicians",
            json={"username": "doctor", "password": "secret"},
            headers=headers(admin, "create-deactivate"),
        )
        path = f"/api/v1/physicians/{created.json()['id']}"
        login(physician, "doctor", "secret", "physician")
        review_response = admin.get(f"{path}/deactivation-review")
        assert review_response.status_code == 200
        review = review_response.json()
        assert review["physician_id"] == created.json()["id"]
        assert review["account_revision"] == created.json()["revision"]
        assert review["drafts"] == []
        assert review["draft_set_revision"]
        assert physician.get(f"{path}/deactivation-review").status_code == 403
        valid_deactivation = {
            "draft_action": "retain",
            "draft_set_revision": review["draft_set_revision"],
        }
        assert (
            physician.post(
                f"{path}/deactivate",
                json=valid_deactivation,
                headers=headers(
                    physician, "forbidden-deactivate", created.headers["etag"]
                ),
            ).status_code
            == 403
        )
        assert (
            physician.post(
                f"{path}/reactivate",
                json={},
                headers=headers(
                    physician, "forbidden-reactivate", created.headers["etag"]
                ),
            ).status_code
            == 403
        )
        assert (
            admin.post(
                f"{path}/deactivate",
                json=valid_deactivation,
                headers={
                    "If-Match": created.headers["etag"],
                    "Idempotency-Key": "no-csrf-state",
                },
            ).status_code
            == 403
        )
        for body in (
            {
                "draft_action": "discard",
                "confirm_discard": False,
                "draft_set_revision": review["draft_set_revision"],
            },
            {"draft_set_revision": review["draft_set_revision"]},
            {"draft_action": "retain"},
            {
                "draft_action": "discard",
                "draft_set_revision": review["draft_set_revision"],
            },
        ):
            assert (
                admin.post(
                    f"{path}/deactivate",
                    json=body,
                    headers=headers(
                        admin, "invalid-deactivate", created.headers["etag"]
                    ),
                ).status_code
                == 422
            )
        assert (
            admin.post(
                f"{path}/deactivate",
                json={"draft_action": "retain", "draft_set_revision": "stale"},
                headers=headers(admin, "stale-drafts", created.headers["etag"]),
            ).status_code
            == 412
        )
        deactivated = admin.post(
            f"{path}/deactivate",
            json={
                "draft_action": "retain",
                "draft_set_revision": review["draft_set_revision"],
            },
            headers=headers(admin, "retain", created.headers["etag"]),
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["active"] is False
        assert physician.get("/api/v1/me").status_code == 401
        with TestClient(app) as probe:
            assert (
                probe.post(
                    "/api/v1/auth/login",
                    json={
                        "username": "doctor",
                        "password": "secret",
                        "role": "physician",
                    },
                ).status_code
                == 401
            )
        reactivated = admin.post(
            f"{path}/reactivate",
            json={},
            headers=headers(admin, "reactivate", deactivated.headers["etag"]),
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["id"] == created.json()["id"]
        assert reactivated.json()["active"] is True
        assert physician.get("/api/v1/me").status_code == 401
        login(physician, "doctor", "secret", "physician")
        assert (
            admin.post(
                f"{path}/deactivate",
                json={
                    "draft_action": "discard",
                    "confirm_discard": True,
                    "draft_set_revision": review["draft_set_revision"],
                },
                headers=headers(admin, "old-review", reactivated.headers["etag"]),
            ).status_code
            == 412
        )
        other = admin.post(
            "/api/v1/physicians",
            json={"username": "other", "password": "secret"},
            headers=headers(admin, "create-other"),
        )
        other_path = f"/api/v1/physicians/{other.json()['id']}"
        other_review = admin.get(f"{other_path}/deactivation-review").json()
        assert (
            admin.post(
                f"{path}/deactivate",
                json={
                    "draft_action": "discard",
                    "confirm_discard": True,
                    "draft_set_revision": other_review["draft_set_revision"],
                },
                headers=headers(admin, "wrong-review", reactivated.headers["etag"]),
            ).status_code
            == 412
        )
        current_review = admin.get(f"{path}/deactivation-review").json()
        discarded = admin.post(
            f"{path}/deactivate",
            json={
                "draft_action": "discard",
                "confirm_discard": True,
                "draft_set_revision": current_review["draft_set_revision"],
            },
            headers=headers(admin, "discard", reactivated.headers["etag"]),
        )
        assert discarded.status_code == 200
        assert discarded.json()["active"] is False
        assert admin.get(path).json() == discarded.json()
        assert physician.get("/api/v1/me").status_code == 401


def test_account_commands_replay_without_duplicate_mutations_or_secret_audit():
    with TestClient(app) as admin, TestClient(app) as physician:
        login(admin)
        admin_id = admin.get("/api/v1/me").json()["id"]
        body = {"username": "doctor", "password": "synthetic-audit-secret"}
        create_headers = headers(admin, "create-once")
        created = admin.post("/api/v1/physicians", json=body, headers=create_headers)
        assert created.status_code == 201
        replay = admin.post("/api/v1/physicians", json=body, headers=create_headers)
        assert replay.status_code == 201
        assert replay.json() == created.json()
        assert replay.headers["etag"] == created.headers["etag"]
        path = f"/api/v1/physicians/{created.json()['id']}"
        assert (
            admin.post(
                "/api/v1/physicians",
                json={**body, "password": "changed-secret"},
                headers=create_headers,
            ).status_code
            == 409
        )
        assert (
            admin.post(
                "/api/v1/physicians",
                json=body,
                headers=headers(admin, "duplicate-name"),
            ).status_code
            == 409
        )
        assert (
            admin.post(
                "/api/v1/physicians",
                json={"username": "missing-key", "password": "x"},
                headers={"X-CSRF-Token": admin.cookies.get("xinsight_csrf")},
            ).status_code
            == 422
        )
        login(physician, "doctor", body["password"], "physician")
        assert physician.get("/api/v1/audit-events").status_code == 403
        assert (
            physician.post(
                "/api/v1/me/password",
                json={
                    "current_password": body["password"],
                    "new_password": "self-audit-secret",
                },
                headers=headers(physician, "self-audit"),
            ).status_code
            == 200
        )
        current = admin.get(path)
        edit_headers = headers(admin, "edit-once", current.headers["etag"])
        renamed = admin.patch(path, json={"username": "renamed"}, headers=edit_headers)
        assert renamed.status_code == 200
        repeated_edit = admin.patch(
            path, json={"username": "renamed"}, headers=edit_headers
        )
        assert repeated_edit.json() == renamed.json()
        assert repeated_edit.status_code == 200
        assert (
            admin.patch(
                path,
                json={"username": "different"},
                headers=edit_headers,
            ).status_code
            == 409
        )
        assert (
            admin.patch(
                path,
                json={"username": "renamed"},
                headers=headers(admin, "edit-once", renamed.headers["etag"]),
            ).status_code
            == 409
        )
        other = admin.post(
            "/api/v1/physicians",
            json={"username": "other", "password": "other-secret"},
            headers=headers(admin, "other"),
        )
        assert other.status_code == 201
        assert (
            admin.patch(
                path,
                json={"username": "other", "password": "must-not-apply"},
                headers=headers(admin, "duplicate-edit", renamed.headers["etag"]),
            ).status_code
            == 409
        )
        assert admin.get(path).json() == renamed.json()
        login(physician, "renamed", "self-audit-secret", "physician")
        review = admin.get(f"{path}/deactivation-review").json()
        deactivate_body = {
            "draft_action": "retain",
            "draft_set_revision": review["draft_set_revision"],
        }
        deactivate_headers = headers(admin, "deactivate-once", renamed.headers["etag"])
        deactivated = admin.post(
            f"{path}/deactivate", json=deactivate_body, headers=deactivate_headers
        )
        assert deactivated.status_code == 200
        repeated_deactivation = admin.post(
            f"{path}/deactivate", json=deactivate_body, headers=deactivate_headers
        )
        assert repeated_deactivation.status_code == 200
        assert repeated_deactivation.json() == deactivated.json()
        assert (
            admin.post(
                f"{path}/deactivate",
                json={
                    **deactivate_body,
                    "draft_action": "discard",
                    "confirm_discard": True,
                },
                headers=deactivate_headers,
            ).status_code
            == 409
        )
        reactivate_headers = headers(
            admin, "reactivate-once", deactivated.headers["etag"]
        )
        reactivated = admin.post(
            f"{path}/reactivate", json={}, headers=reactivate_headers
        )
        assert reactivated.status_code == 200
        repeated_reactivation = admin.post(
            f"{path}/reactivate", json={}, headers=reactivate_headers
        )
        assert repeated_reactivation.status_code == 200
        assert repeated_reactivation.json() == reactivated.json()
        assert admin.get(path).json() == reactivated.json()
        # Retrying old create returns its original safe representation.
        assert (
            admin.post("/api/v1/physicians", json=body, headers=create_headers).json()
            == created.json()
        )
        events_response = admin.get("/api/v1/audit-events")
        assert events_response.status_code == 200
        events = events_response.json()["items"]
        account_events = [
            event for event in events if event["operation"].startswith("physician.")
        ]
        assert [event["operation"] for event in account_events].count(
            "physician.create"
        ) == 2
        assert [event["operation"] for event in account_events].count(
            "physician.edit"
        ) == 1
        assert [event["operation"] for event in account_events].count(
            "physician.deactivate"
        ) == 1
        assert [event["operation"] for event in account_events].count(
            "physician.reactivate"
        ) == 1
        assert all(
            event["actor_id"] == admin_id and event["actor_display"] == "admin"
            for event in account_events
        )
        creation = next(
            event
            for event in account_events
            if event["operation"] == "physician.create"
            and event["result_reference"] == created.json()["id"]
        )
        assert creation["target_display"] == "doctor"
        own_change = next(
            event for event in events if event["operation"] == "auth.password_change"
        )
        assert own_change["actor_id"] == created.json()["id"]
        assert own_change["actor_display"] == "doctor"
        deactivation = next(
            event
            for event in account_events
            if event["operation"] == "physician.deactivate"
        )
        assert deactivation["details"]["draft_action"] == "retain"
        assert (
            deactivation["details"]["draft_set_revision"]
            == review["draft_set_revision"]
        )
        for secret in (
            body["password"],
            "self-audit-secret",
            "changed-secret",
            "must-not-apply",
            "other-secret",
            "pbkdf2",
            "password_hash",
            "request_hash",
        ):
            assert secret not in events_response.text
        assert len(admin.get("/api/v1/physicians").json()["items"]) == 2


def test_idempotency_detects_changed_username_spelling_before_normalization():
    with TestClient(app) as admin:
        login(admin)
        request_headers = headers(admin, "case-sensitive-replay")
        created = admin.post(
            "/api/v1/physicians",
            json={"username": "Doctor", "password": "secret"},
            headers=request_headers,
        )
        assert created.status_code == 201
        assert created.json()["username"] == "doctor"
        assert (
            admin.post(
                "/api/v1/physicians",
                json={"username": "doctor", "password": "secret"},
                headers=request_headers,
            ).status_code
            == 409
        )
        assert (
            admin.post(
                "/api/v1/physicians",
                json={"username": " DOCTOR ", "password": "secret"},
                headers=headers(admin, "normalized-duplicate"),
            ).status_code
            == 409
        )
        assert len(admin.get("/api/v1/physicians").json()["items"]) == 1
