from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import OperationalError

from app.api import health
from app.db import health as db_health
from app.main import app


def test_database_health_returns_success_when_connection_is_verified(monkeypatch) -> None:
    check = MagicMock(return_value=True)
    monkeypatch.setattr(health, "check_database_connection", check)

    with TestClient(app) as client:
        response = client.get("/api/health/database")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}
    check.assert_called_once_with()


def test_database_health_returns_generic_unavailable_response(monkeypatch) -> None:
    check = MagicMock(return_value=False)
    monkeypatch.setattr(health, "check_database_connection", check)

    with TestClient(app) as client:
        response = client.get("/api/health/database")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database connection unavailable"}
    check.assert_called_once_with()


def test_connection_check_executes_select_one_without_a_real_database(monkeypatch) -> None:
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = 1
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(db_health, "engine", engine)

    assert db_health.check_database_connection() is True
    query = connection.execute.call_args.args[0]
    assert str(query) == "SELECT 1"
    engine.connect.return_value.__exit__.assert_called_once()


def test_connection_check_handles_database_errors_without_exposing_them(
    monkeypatch,
) -> None:
    engine = MagicMock()
    engine.connect.side_effect = OperationalError(
        "SELECT 1",
        {},
        RuntimeError("private connection detail"),
    )
    monkeypatch.setattr(db_health, "engine", engine)

    assert db_health.check_database_connection() is False
