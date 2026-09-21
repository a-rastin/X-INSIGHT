from fastapi.testclient import TestClient

from x_insight.app import app


def test_process_reports_liveness() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
