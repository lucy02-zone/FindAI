from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_healthy_status() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": "FindAI",
        "version": "0.1.0",
    }
