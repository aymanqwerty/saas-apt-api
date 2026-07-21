from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_success_envelope() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "connected"
