from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.api import auth, dependencies
from app.core.config import Settings
from app.schemas.user import UserResponse

TEST_SECRET = "test-only-signing-secret-with-at-least-32-bytes"


@pytest.fixture
def auth_settings(monkeypatch):
    configured = Settings(
        JWT_SECRET_KEY=TEST_SECRET,
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
    )
    monkeypatch.setattr(dependencies, "settings", configured)
    return configured


def make_token(secret=TEST_SECRET, subject="42", expires_at=None):
    return jwt.encode(
        {
            "sub": subject,
            "exp": expires_at or datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )


def credentials(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def profile_user():
    return SimpleNamespace(
        id=42,
        username="alice",
        email="alice@example.com",
        is_active=True,
        created_at=datetime(2026, 10, 28, 12, 0, 0),
        hashed_password="private-password-hash",
    )


def test_current_user_dependency_loads_user_for_valid_token(auth_settings):
    user = profile_user()
    db = Mock()
    db.scalar.return_value = user

    result = dependencies.get_current_user(credentials(make_token()), db)

    assert result is user
    query = db.scalar.call_args.args[0]
    assert "users.id = 42" in str(query.compile(compile_kwargs={"literal_binds": True}))


def test_current_user_dependency_rejects_missing_token():
    db = Mock()

    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(None, db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    db.scalar.assert_not_called()


@pytest.mark.parametrize(
    "token",
    ["not-a-jwt", make_token(secret="different-signing-secret-with-at-least-32-bytes")],
    ids=["malformed", "invalid-signature"],
)
def test_current_user_dependency_rejects_invalid_token(token, auth_settings):
    db = Mock()

    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(credentials(token), db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    db.scalar.assert_not_called()


def test_current_user_dependency_rejects_expired_token(auth_settings):
    token = make_token(expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
    db = Mock()

    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(credentials(token), db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    db.scalar.assert_not_called()


@pytest.mark.parametrize(
    "subject",
    ["not-an-id", "0", "-42", "2147483648", ""],
)
def test_current_user_dependency_rejects_unusable_subject(subject, auth_settings):
    db = Mock()

    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(credentials(make_token(subject=subject)), db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    db.scalar.assert_not_called()


def test_current_user_dependency_rejects_non_bearer_scheme(auth_settings):
    db = Mock()
    basic_credentials = HTTPAuthorizationCredentials(
        scheme="Basic",
        credentials=make_token(),
    )

    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(basic_credentials, db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    db.scalar.assert_not_called()


def test_current_user_dependency_rejects_deleted_user(auth_settings):
    db = Mock()
    db.scalar.return_value = None

    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(credentials(make_token()), db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}


def test_me_returns_safe_profile_fields_only():
    response = auth.read_current_user(profile_user())
    result = response.model_dump()

    assert isinstance(response, UserResponse)
    assert result["id"] == 42
    assert result["username"] == "alice"
    assert result["email"] == "alice@example.com"
    assert "hashed_password" not in result
    assert "password" not in result
    assert "JWT_SECRET_KEY" not in result
    route = next(route for route in auth.router.routes if route.path == "/me")
    assert route.response_model is UserResponse
