from fastapi.testclient import TestClient


def test_health_returns_ok_and_environment(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"status": "ok", "environment": "test"}
    assert body["meta"]["request_id"] == response.headers["X-Request-ID"]
    assert isinstance(body["meta"]["processing_time_ms"], int)
