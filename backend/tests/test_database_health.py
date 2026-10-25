import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import OperationalError

from app.api import health
from app.db import health as db_health
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


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


def test_database_health_handler_raises_generic_503_when_check_fails(monkeypatch) -> None:
    check = MagicMock(return_value=False)
    monkeypatch.setattr(health, "check_database_connection", check)

    with pytest.raises(HTTPException) as error:
        health.database_health_check()

    assert error.value.status_code == 503
    assert error.value.detail == "Database connection unavailable"
    assert "private" not in error.value.detail
    assert "SELECT" not in error.value.detail
    assert "mysql" not in error.value.detail.lower()


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


def test_connection_check_releases_connection_when_query_fails(monkeypatch) -> None:
    connection = MagicMock()
    connection.execute.side_effect = OperationalError(
        "SELECT 1",
        {},
        RuntimeError("private query detail"),
    )
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    engine.connect.return_value.__exit__.return_value = False
    monkeypatch.setattr(db_health, "engine", engine)

    assert db_health.check_database_connection() is False
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


def test_application_import_does_not_attempt_a_database_connection() -> None:
    environment = os.environ.copy()
    environment["DB_HOST"] = "127.0.0.1"
    environment["DB_PORT"] = "1"
    environment["DB_PASSWORD"] = ""

    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0
