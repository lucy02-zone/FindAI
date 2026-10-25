from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_root_returns_welcome_message_and_docs_path() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert payload["message"] == f"Welcome to {settings.APP_NAME}"
    assert payload["docs"] == "/docs"
