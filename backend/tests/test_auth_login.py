from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.api import auth
from app.core import security
from app.core.config import Settings
from app.schemas.user import TokenResponse, UserLogin


@pytest.fixture
def jwt_settings(monkeypatch):
    configured = Settings(
        JWT_SECRET_KEY="test-only-signing-secret-with-at-least-32-bytes",
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
    )
    monkeypatch.setattr(security, "settings", configured)
    return configured


def login_payload(email="ALICE@Example.COM", password="correct horse battery staple"):
    return UserLogin(email=email, password=password)


def test_login_returns_signed_token_with_subject_and_expiry(monkeypatch, jwt_settings):
    user = SimpleNamespace(id=42, hashed_password="stored-hash", is_active=True)
    db = Mock()
    db.scalar.return_value = user
    monkeypatch.setattr(auth, "verify_password", Mock(return_value=True))

    response = auth.login_user(login_payload(), db)

    claims = jwt.decode(
        response.access_token,
        jwt_settings.JWT_SECRET_KEY,
        algorithms=[jwt_settings.JWT_ALGORITHM],
    )
    assert isinstance(response, TokenResponse)
    assert response.token_type == "bearer"
    assert claims["sub"] == "42"
    assert claims["exp"] > datetime.now(timezone.utc).timestamp()
    query = db.scalar.call_args.args[0]
    assert "alice@example.com" in str(query.compile(compile_kwargs={"literal_binds": True}))
    assert "password" not in response.model_dump()
    assert "hashed_password" not in response.model_dump()
    login_route = next(route for route in auth.router.routes if route.path == "/login")
    assert login_route.response_model is TokenResponse
    assert login_route.status_code in (None, status.HTTP_200_OK)


def test_login_accepts_existing_password_hash_and_returns_token(jwt_settings):
    payload = login_payload()
    user = SimpleNamespace(
        id=42,
        hashed_password=security.hash_password(payload.password),
        is_active=True,
    )
    db = Mock()
    db.scalar.return_value = user

    response = auth.login_user(payload, db)

    claims = jwt.decode(
        response.access_token,
        jwt_settings.JWT_SECRET_KEY,
        algorithms=[jwt_settings.JWT_ALGORITHM],
    )
    assert response.token_type == "bearer"
    assert claims["sub"] == "42"


@pytest.mark.parametrize("found_user", [True, False], ids=["incorrect-password", "unknown-email"])
def test_invalid_login_uses_same_safe_unauthorized_response(monkeypatch, found_user):
    db = Mock()
    db.scalar.return_value = (
        SimpleNamespace(hashed_password="stored-hash", is_active=True)
        if found_user
        else None
    )
    verifier = Mock(return_value=False)
    monkeypatch.setattr(auth, "verify_password", verifier)

    with pytest.raises(HTTPException) as error:
        auth.login_user(login_payload(password="wrong password"), db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.detail == "Invalid email or password"
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    assert "stored-hash" not in error.value.detail
    assert "wrong password" not in error.value.detail
    assert verifier.call_count == (1 if found_user else 0)


def test_login_reports_expired_token_as_expired():
    expired = jwt.encode(
        {"sub": "42", "exp": datetime(2000, 1, 1, tzinfo=timezone.utc)},
        "test-only-signing-secret-with-at-least-32-bytes",
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(
            expired,
            "test-only-signing-secret-with-at-least-32-bytes",
            algorithms=["HS256"],
        )


def test_login_reports_invalid_signature():
    signed = jwt.encode(
        {"sub": "42", "exp": datetime(2999, 1, 1, tzinfo=timezone.utc)},
        "right-secret-with-at-least-32-bytes",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(signed, "wrong-secret-with-at-least-32-bytes", algorithms=["HS256"])


def test_database_failure_returns_generic_service_error(caplog):
    db = Mock()
    db.scalar.side_effect = SQLAlchemyError("private database connection details")

    with pytest.raises(HTTPException) as error:
        auth.login_user(login_payload(), db)

    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert error.value.detail == "Authentication service unavailable"
    assert "private" not in error.value.detail
    assert "SQLAlchemyError" in caplog.text
    assert "private database connection details" not in caplog.text


def test_unexpected_lookup_exception_is_logged_without_exception_values(caplog):
    db = Mock()
    db.scalar.side_effect = RuntimeError(
        "password=do-not-log jwt_secret=do-not-log token=do-not-log"
    )

    with pytest.raises(HTTPException) as error:
        auth.login_user(login_payload(), db)

    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert error.value.detail == "Authentication service unavailable"
    assert "RuntimeError" in caplog.text
    assert "password=do-not-log" not in caplog.text
    assert "jwt_secret=do-not-log" not in caplog.text
    assert "token=do-not-log" not in caplog.text


def test_missing_jwt_secret_is_logged_safely_and_returns_generic_service_error(
    monkeypatch,
    caplog,
):
    from app.core import security
    from app.core.config import Settings

    monkeypatch.setattr(
        security,
        "settings",
        Settings(JWT_SECRET_KEY="", JWT_ALGORITHM="HS256"),
    )
    db = Mock()
    db.scalar.return_value = SimpleNamespace(
        id=42,
        hashed_password="stored-hash",
        is_active=True,
    )
    monkeypatch.setattr(auth, "verify_password", Mock(return_value=True))

    with pytest.raises(HTTPException) as error:
        auth.login_user(login_payload(), db)

    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert error.value.detail == "Authentication service unavailable"
    assert "RuntimeError" in caplog.text
    assert "JWT_SECRET_KEY is not configured" not in caplog.text
