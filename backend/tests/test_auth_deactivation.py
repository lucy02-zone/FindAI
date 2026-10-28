from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import SQLAlchemyError

from app.api import auth, dependencies
from app.core.config import Settings
from app.core.security import hash_password
from app.schemas.user import (
    AccountDeactivationRequest,
    AccountDeactivationResponse,
    UserLogin,
)

TEST_SECRET = "test-only-signing-secret-with-at-least-32-bytes"


@pytest.fixture
def jwt_settings(monkeypatch):
    configured = Settings(
        JWT_SECRET_KEY=TEST_SECRET,
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
    )
    monkeypatch.setattr(dependencies, "settings", configured)
    return configured


def user_with_password():
    return SimpleNamespace(
        id=42,
        username="alice",
        email="alice@example.com",
        is_active=True,
        hashed_password=hash_password("correct horse battery staple"),
        created_at=datetime(2026, 10, 28, 12, 0, 0),
    )


def make_token():
    return jwt.encode(
        {
            "sub": "42",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        TEST_SECRET,
        algorithm="HS256",
    )


def test_successful_deactivation_soft_disables_user_without_exposing_secrets():
    user = user_with_password()
    db = Mock()

    response = auth.deactivate_account(
        AccountDeactivationRequest(current_password="correct horse battery staple"),
        current_user=user,
        db=db,
    )

    assert isinstance(response, AccountDeactivationResponse)
    assert response.model_dump() == {"message": "Account deactivated successfully"}
    assert user.is_active is False
    assert user.id == 42
    assert user.username == "alice"
    assert user.email == "alice@example.com"
    assert "password" not in response.model_dump()
    assert "hashed_password" not in response.model_dump()
    db.commit.assert_called_once_with()
    db.delete.assert_not_called()
    db.rollback.assert_not_called()


def test_incorrect_password_does_not_deactivate_account():
    user = user_with_password()
    db = Mock()

    with pytest.raises(HTTPException) as error:
        auth.deactivate_account(
            AccountDeactivationRequest(current_password="incorrect password"),
            current_user=user,
            db=db,
        )

    assert error.value.status_code == status.HTTP_400_BAD_REQUEST
    assert error.value.detail == "Current password is incorrect"
    assert "incorrect password" not in error.value.detail
    assert user.is_active is True
    db.commit.assert_not_called()


def test_deactivation_database_error_rolls_back_safely():
    user = user_with_password()
    db = Mock()
    db.commit.side_effect = SQLAlchemyError("private database details")

    with pytest.raises(HTTPException) as error:
        auth.deactivate_account(
            AccountDeactivationRequest(current_password="correct horse battery staple"),
            current_user=user,
            db=db,
        )

    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert error.value.detail == "Account deactivation service unavailable"
    assert "private" not in error.value.detail
    db.rollback.assert_called_once_with()


def test_login_rejects_deactivated_user_with_generic_unauthorized(monkeypatch):
    user = user_with_password()
    user.is_active = False
    db = Mock()
    db.scalar.return_value = user
    verifier = Mock()
    monkeypatch.setattr(auth, "verify_password", verifier)

    with pytest.raises(HTTPException) as error:
        auth.login_user(
            UserLogin(email="alice@example.com", password="correct horse battery staple"),
            db,
        )

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.detail == "Invalid email or password"
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    verifier.assert_not_called()


def test_previously_issued_token_is_rejected_after_deactivation(jwt_settings):
    user = user_with_password()
    user.is_active = False
    db = Mock()
    db.scalar.return_value = user
    token = make_token()
    bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(bearer, db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}


def test_deactivation_requires_existing_current_user_dependency():
    route = next(route for route in auth.router.routes if route.path == "/deactivate")

    assert "POST" in route.methods
    assert route.response_model is AccountDeactivationResponse
    assert any(
        dependency.call is dependencies.get_current_user
        for dependency in route.dependant.dependencies
    )
