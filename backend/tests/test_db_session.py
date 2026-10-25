from unittest.mock import Mock

import pytest

from app.core.config import settings
from app.db import session as db_session


def test_database_url_uses_mysql_settings() -> None:
    url = db_session.DATABASE_URL

    assert url.drivername == "mysql+pymysql"
    assert url.username == settings.DB_USER
    assert url.password == settings.DB_PASSWORD
    assert url.host == settings.DB_HOST
    assert url.port == settings.DB_PORT
    assert url.database == settings.DB_NAME


def test_session_factory_is_configured_without_autocommit_or_autoflush() -> None:
    assert db_session.SessionLocal.kw["bind"] is db_session.engine
    assert db_session.SessionLocal.kw["autocommit"] is False
    assert db_session.SessionLocal.kw["autoflush"] is False


def test_engine_uses_small_pre_pinged_connection_pool() -> None:
    pool = db_session.engine.pool

    assert pool.size() == 5
    assert pool._max_overflow == 10
    assert pool._pre_ping is True


def test_get_db_closes_session(monkeypatch) -> None:
    mocked_db = Mock()
    mocked_factory = Mock(return_value=mocked_db)
    monkeypatch.setattr(db_session, "SessionLocal", mocked_factory)

    dependency = db_session.get_db()
    assert next(dependency) is mocked_db

    dependency.close()

    mocked_factory.assert_called_once_with()
    mocked_db.close.assert_called_once_with()


def test_get_db_closes_session_when_consumer_raises(monkeypatch) -> None:
    mocked_db = Mock()
    mocked_factory = Mock(return_value=mocked_db)
    monkeypatch.setattr(db_session, "SessionLocal", mocked_factory)

    dependency = db_session.get_db()
    assert next(dependency) is mocked_db

    with pytest.raises(RuntimeError, match="endpoint failed"):
        dependency.throw(RuntimeError("endpoint failed"))

    mocked_db.close.assert_called_once_with()
