from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api import auth, dependencies
from app.core.security import hash_password, verify_password
from app.schemas.user import PasswordChangeRequest, PasswordChangeResponse


def user_with_password(password="old secure password"):
    return SimpleNamespace(
        id=42,
        username="alice",
        email="alice@example.com",
        is_active=True,
        created_at=datetime(2026, 10, 28, 12, 0, 0),
        hashed_password=hash_password(password),
    )


def test_successful_password_change_replaces_hash_without_exposing_it():
    user = user_with_password()
    original_hash = user.hashed_password
    db = Mock()

    response = auth.change_password(
        PasswordChangeRequest(
            current_password="old secure password",
            new_password="new secure password",
        ),
        current_user=user,
        db=db,
    )

    assert isinstance(response, PasswordChangeResponse)
    assert response.model_dump() == {"message": "Password updated successfully"}
    assert user.hashed_password != original_hash
    assert verify_password("new secure password", user.hashed_password)
    assert not verify_password("old secure password", user.hashed_password)
    assert user.id == 42
    assert user.username == "alice"
    assert user.email == "alice@example.com"
    assert "password" not in response.model_dump()
    assert "hashed_password" not in response.model_dump()
    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()


def test_incorrect_current_password_returns_safe_bad_request(monkeypatch):
    user = user_with_password()
    db = Mock()
    hasher = Mock()
    monkeypatch.setattr(auth, "hash_password", hasher)

    with pytest.raises(HTTPException) as error:
        auth.change_password(
            PasswordChangeRequest(
                current_password="wrong password",
                new_password="new secure password",
            ),
            current_user=user,
            db=db,
        )

    assert error.value.status_code == status.HTTP_400_BAD_REQUEST
    assert error.value.detail == "Current password is incorrect"
    assert "wrong password" not in error.value.detail
    hasher.assert_not_called()
    db.commit.assert_not_called()


def test_identical_current_and_new_password_is_rejected(monkeypatch):
    user = user_with_password()
    db = Mock()
    hasher = Mock()
    monkeypatch.setattr(auth, "hash_password", hasher)

    with pytest.raises(HTTPException) as error:
        auth.change_password(
            PasswordChangeRequest(
                current_password="old secure password",
                new_password="old secure password",
            ),
            current_user=user,
            db=db,
        )

    assert error.value.status_code == status.HTTP_400_BAD_REQUEST
    assert error.value.detail == "New password must differ from the current password"
    hasher.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    "data",
    [
        {"current_password": "old secure password", "new_password": "short"},
        {
            "current_password": "old secure password",
            "new_password": "x" * 129,
        },
        {"current_password": "", "new_password": "new secure password"},
        {
            "current_password": "old secure password",
            "new_password": "new secure password",
            "username": "attacker",
        },
    ],
)
def test_password_change_rejects_invalid_or_extra_fields(data):
    with pytest.raises(ValidationError):
        PasswordChangeRequest.model_validate(data)


def test_password_database_error_rolls_back_and_returns_generic_response(monkeypatch):
    user = user_with_password()
    db = Mock()
    db.commit.side_effect = SQLAlchemyError("private database failure")
    monkeypatch.setattr(auth, "hash_password", Mock(return_value="new-hash"))

    with pytest.raises(HTTPException) as error:
        auth.change_password(
            PasswordChangeRequest(
                current_password="old secure password",
                new_password="new secure password",
            ),
            current_user=user,
            db=db,
        )

    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert error.value.detail == "Password change service unavailable"
    assert "private" not in error.value.detail
    db.rollback.assert_called_once_with()


def test_password_route_requires_current_user_dependency():
    route = next(route for route in auth.router.routes if route.path == "/change-password")

    assert route.response_model is PasswordChangeResponse
    assert any(
        dependency.call is dependencies.get_current_user
        for dependency in route.dependant.dependencies
    )
