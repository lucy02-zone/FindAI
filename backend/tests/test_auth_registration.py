from datetime import datetime
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status
from pydantic import ValidationError

from app.api import auth
from app.schemas.user import UserCreate, UserResponse


def registration_route():
    return next(route for route in auth.router.routes if route.path == "/register")


def populate_created_user(user) -> None:
    user.id = 42
    user.is_active = True
    user.created_at = datetime(2026, 10, 25, 12, 0, 0)


def test_registration_creates_user_with_hashed_password_and_safe_response(
    monkeypatch,
) -> None:
    db = Mock()
    db.scalar.side_effect = [None, None]
    db.refresh.side_effect = populate_created_user
    hasher = Mock(return_value="argon2-hash-value")
    monkeypatch.setattr(auth, "hash_password", hasher)
    payload = UserCreate(
        username="alice",
        email="ALICE@Example.COM",
        password="strong passphrase",
    )

    response = auth.register_user(payload, db)

    assert isinstance(response, UserResponse)
    assert response.model_dump() == {
        "id": 42,
        "username": "alice",
        "email": "alice@example.com",
        "is_active": True,
        "created_at": datetime(2026, 10, 25, 12, 0, 0),
    }
    assert "password" not in response.model_dump()
    assert "hashed_password" not in response.model_dump()
    assert registration_route().status_code == status.HTTP_201_CREATED
    assert registration_route().response_model is UserResponse
    hasher.assert_called_once_with(payload.password)
    persisted_user = db.add.call_args.args[0]
    assert persisted_user.email == "alice@example.com"
    assert persisted_user.hashed_password == "argon2-hash-value"
    assert persisted_user.hashed_password != payload.password
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(persisted_user)


def test_registration_rejects_duplicate_email(monkeypatch) -> None:
    db = Mock()
    db.scalar.return_value = 12
    hasher = Mock()
    monkeypatch.setattr(auth, "hash_password", hasher)
    payload = UserCreate(
        username="alice",
        email="ALICE@example.com",
        password="strong passphrase",
    )

    with pytest.raises(HTTPException) as error:
        auth.register_user(payload, db)

    assert error.value.status_code == status.HTTP_409_CONFLICT
    assert error.value.detail == "Email already registered"
    duplicate_lookup = db.scalar.call_args.args[0]
    assert "alice@example.com" in str(
        duplicate_lookup.compile(compile_kwargs={"literal_binds": True})
    )
    hasher.assert_not_called()
    db.add.assert_not_called()


def test_registration_rejects_duplicate_username(monkeypatch) -> None:
    db = Mock()
    db.scalar.side_effect = [None, 12]
    hasher = Mock()
    monkeypatch.setattr(auth, "hash_password", hasher)
    payload = UserCreate(
        username="alice",
        email="alice@example.com",
        password="strong passphrase",
    )

    with pytest.raises(HTTPException) as error:
        auth.register_user(payload, db)

    assert error.value.status_code == status.HTTP_409_CONFLICT
    assert error.value.detail == "Username already registered"
    hasher.assert_not_called()
    db.add.assert_not_called()


def test_registration_rejects_invalid_input_before_database_access() -> None:
    db = Mock()

    with pytest.raises(ValidationError):
        UserCreate(username="ab", email="invalid-email", password="short")

    db.scalar.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_integrity_error_rolls_back_and_returns_generic_conflict(monkeypatch) -> None:
    db = Mock()
    db.scalar.side_effect = [None, None]
    db.commit.side_effect = IntegrityError(
        "INSERT INTO users",
        {},
        RuntimeError("private database detail"),
    )
    monkeypatch.setattr(auth, "hash_password", Mock(return_value="argon2-hash"))
    payload = UserCreate(
        username="alice",
        email="alice@example.com",
        password="strong passphrase",
    )

    with pytest.raises(HTTPException) as error:
        auth.register_user(payload, db)

    assert error.value.status_code == status.HTTP_409_CONFLICT
    assert error.value.detail == "Email or username already registered"
    assert "private" not in error.value.detail
    assert "INSERT" not in error.value.detail
    db.rollback.assert_called_once_with()
