from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api import dependencies, users
from app.schemas.user import UserProfileUpdate, UserResponse


def make_user():
    return SimpleNamespace(
        id=42,
        username="alice",
        email="alice@example.com",
        is_active=True,
        created_at=datetime(2026, 10, 28, 12, 0, 0),
        hashed_password="must-not-be-returned",
    )


def test_updates_username_and_returns_safe_profile():
    user = make_user()
    db = Mock()
    db.scalar.return_value = None

    response = users.update_current_user(
        UserProfileUpdate(username="  alice_new  "),
        current_user=user,
        db=db,
    )

    assert isinstance(response, UserResponse)
    assert response.username == "alice_new"
    assert response.email == "alice@example.com"
    assert "hashed_password" not in response.model_dump()
    assert "password" not in response.model_dump()
    query = db.scalar.call_args.args[0]
    assert "users.username = 'alice_new'" in str(
        query.compile(compile_kwargs={"literal_binds": True})
    )
    assert "users.id != 42" in str(query.compile(compile_kwargs={"literal_binds": True}))
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(user)


def test_updates_email_with_registration_normalization_and_preserves_username():
    user = make_user()
    db = Mock()
    db.scalar.return_value = None

    response = users.update_current_user(
        UserProfileUpdate(email="  ALICE.NEW@Example.COM  "),
        current_user=user,
        db=db,
    )

    assert response.email == "alice.new@example.com"
    assert response.username == "alice"
    assert user.email == "alice.new@example.com"


def test_rejects_profile_update_with_no_effective_changes():
    user = make_user()
    db = Mock()

    with pytest.raises(HTTPException) as error:
        users.update_current_user(
            UserProfileUpdate(username="alice"),
            current_user=user,
            db=db,
        )

    assert error.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    db.scalar.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    ("payload", "existing_id", "detail"),
    [
        (UserProfileUpdate(username="bob"), 7, "Username already registered"),
        (
            UserProfileUpdate(email="bob@example.com"),
            7,
            "Email already registered",
        ),
    ],
)
def test_duplicate_username_or_email_returns_conflict_without_mutating_user(
    payload,
    existing_id,
    detail,
):
    user = make_user()
    db = Mock()
    db.scalar.return_value = existing_id

    with pytest.raises(HTTPException) as error:
        users.update_current_user(payload, current_user=user, db=db)

    assert error.value.status_code == status.HTTP_409_CONFLICT
    assert error.value.detail == detail
    assert user.username == "alice"
    assert user.email == "alice@example.com"
    db.commit.assert_not_called()


def test_integrity_error_rolls_back_and_returns_safe_conflict():
    user = make_user()
    db = Mock()
    db.scalar.return_value = None
    db.commit.side_effect = IntegrityError(
        "UPDATE users",
        {},
        RuntimeError("private database constraint details"),
    )

    with pytest.raises(HTTPException) as error:
        users.update_current_user(
            UserProfileUpdate(username="alice_new"),
            current_user=user,
            db=db,
        )

    assert error.value.status_code == status.HTTP_409_CONFLICT
    assert error.value.detail == "Username or email already registered"
    assert "private" not in error.value.detail
    db.rollback.assert_called_once_with()


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"username": None},
        {"email": None},
        {"username": "ab"},
        {"username": "  "},
        {"username": "x" * 51},
        {"email": "not-an-email"},
        {"id": 7},
        {"hashed_password": "attacker-value"},
        {"password": "new password"},
        {"is_active": False},
    ],
)
def test_rejects_empty_invalid_or_restricted_profile_updates(data):
    with pytest.raises(ValidationError):
        UserProfileUpdate.model_validate(data)


def test_user_update_route_is_protected_and_uses_safe_response_schema():
    route = next(route for route in users.router.routes if route.path == "/me")

    assert "PATCH" in route.methods
    assert route.response_model is UserResponse
    assert any(
        dependency.call is dependencies.get_current_user
        for dependency in route.dependant.dependencies
    )
