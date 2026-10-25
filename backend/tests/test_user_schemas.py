from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate, UserLogin, UserResponse


def test_valid_user_registration_trims_username() -> None:
    registration = UserCreate(
        username="  alice  ",
        email="alice@example.com",
        password="strong passphrase",
    )

    assert registration.username == "alice"
    assert str(registration.email) == "alice@example.com"
    assert registration.password == "strong passphrase"


def test_valid_login_request() -> None:
    login = UserLogin(email="alice@example.com", password="strong passphrase")

    assert str(login.email) == "alice@example.com"
    assert login.password == "strong passphrase"


def test_registration_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            username="alice",
            email="not-an-email",
            password="strong passphrase",
        )


def test_registration_rejects_username_shorter_than_three_characters() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            username=" ab ",
            email="alice@example.com",
            password="strong passphrase",
        )


def test_registration_rejects_password_shorter_than_eight_characters() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            username="alice",
            email="alice@example.com",
            password="short7",
        )


def test_user_response_is_orm_compatible_and_excludes_passwords() -> None:
    created_at = datetime(2026, 10, 25, 12, 0, 0)
    orm_user = SimpleNamespace(
        id=7,
        username="alice",
        email="alice@example.com",
        is_active=True,
        created_at=created_at,
        hashed_password="stored-hash-must-not-be-exposed",
        password="plaintext-must-not-be-exposed",
    )

    response = UserResponse.model_validate(orm_user)
    result = response.model_dump()

    assert result == {
        "id": 7,
        "username": "alice",
        "email": "alice@example.com",
        "is_active": True,
        "created_at": created_at,
    }
    assert "hashed_password" not in result
    assert "password" not in result
