from fastapi.testclient import TestClient

from x_insight.app import app, register_exception_handlers
from x_insight.contracts import MAX_BODY_BYTES


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_ready_reports_ready_when_database_migrated() -> None:
    with _client() as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["x-request-id"]


def test_ready_reports_unavailable_when_database_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://xinsight:x@localhost:5999/nope")
    with _client() as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "UNAVAILABLE"
    assert body["request_id"] == response.headers["x-request-id"]
    assert body["retryable"] is True
    assert "traceback" not in response.text.lower()
    assert "xinsight" not in response.text.lower()
    assert "5999" not in response.text


def test_unknown_route_returns_standard_envelope_with_correlation() -> None:
    with _client() as client:
        response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["message"]
    assert body["field_errors"] == {}
    assert body["retryable"] is False
    assert body["request_id"] == response.headers["x-request-id"]
    assert "traceback" not in response.text.lower()


def test_client_request_id_is_propagated() -> None:
    with _client() as client:
        response = client.get(
            "/api/v1/does-not-exist", headers={"X-Request-ID": "probe-123"}
        )
    assert response.status_code == 404
    assert response.headers["x-request-id"] == "probe-123"
    assert response.json()["request_id"] == "probe-123"


def test_health_does_not_require_database(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://xinsight:x@localhost:5999/nope")
    with _client() as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_oversized_body_returns_413_envelope() -> None:
    big = b"x" * (MAX_BODY_BYTES + 1)
    with _client() as client:
        response = client.post(
            "/api/v1/ready", content=big, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 413
    body = response.json()
    assert body["code"] == "PAYLOAD_TOO_LARGE"
    assert body["request_id"] == response.headers["x-request-id"]


def test_validation_errors_use_standard_envelope() -> None:
    from fastapi import FastAPI  # local import: dummy route lives only in this test
    from pydantic import BaseModel

    local = FastAPI()
    register_exception_handlers(local)

    class Item(BaseModel):
        age: int

    @local.post("/items")
    def create(item: Item) -> dict[str, int]:
        return {"age": item.age}

    with TestClient(local, raise_server_exceptions=False) as client:
        response = client.post("/items", json={"age": "not-an-int"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INVALID_CONTENT"
    assert body["field_errors"]
    assert body["request_id"]
    assert "traceback" not in response.text.lower()


def test_ready_reports_incompatible_when_schema_missing(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://xinsight:xinsight_dev@localhost:5432/postgres",
    )
    with _client() as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "INCOMPATIBLE_SCHEMA"
