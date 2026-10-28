from datetime import date, datetime
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api import dependencies, items
from app.core.config import Settings
from app.db.base import Base
from app.main import app
from app.models import LostItem, User
from app.schemas.item import LostItemResponse, LostItemUpdate

TEST_SECRET = "test-only-signing-secret-with-at-least-32-bytes"
OLD_CREATED_AT = datetime(2020, 1, 1, 10, 0, 0)
OLD_UPDATED_AT = datetime(2020, 1, 2, 10, 0, 0)


@pytest.fixture
def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def create_user(db, username, email):
    user = User(
        username=username,
        email=email,
        hashed_password="private-test-hash",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_item(db, owner):
    lost_item = LostItem(
        title="Red backpack",
        description="Contains a notebook",
        category="accessories",
        location="Central Library",
        date_lost=date(2026, 10, 25),
        image_path="private/internal/image.jpg",
        status="open",
        user_id=owner.id,
        created_at=OLD_CREATED_AT,
        updated_at=OLD_UPDATED_AT,
    )
    db.add(lost_item)
    db.commit()
    db.refresh(lost_item)
    return lost_item


def test_owner_can_update_item_and_gets_safe_response(database_session):
    owner = create_user(database_session, "alice", "alice@example.com")
    lost_item = create_item(database_session, owner)

    response = items.update_lost_item(
        lost_item.id,
        LostItemUpdate(
            title="  Blue backpack ",
            description="  Has a notebook and keys.  ",
            category="  accessories  ",
            location="  North Library  ",
            date_lost=date(2026, 10, 27),
        ),
        owner,
        database_session,
    )

    assert isinstance(response, LostItemResponse)
    assert response.title == "Blue backpack"
    assert response.description == "Has a notebook and keys."
    assert response.category == "accessories"
    assert response.location == "North Library"
    assert response.date_lost == date(2026, 10, 27)
    assert response.id == lost_item.id
    assert response.user_id == owner.id
    assert response.status == "open"
    assert response.created_at == OLD_CREATED_AT
    assert response.updated_at > OLD_UPDATED_AT
    result = response.model_dump()
    assert "image_path" not in result
    assert "hashed_password" not in result


def test_partial_update_changes_only_provided_field(database_session):
    owner = create_user(database_session, "alice", "alice@example.com")
    lost_item = create_item(database_session, owner)

    response = items.update_lost_item(
        lost_item.id,
        LostItemUpdate(location="  East Entrance  "),
        owner,
        database_session,
    )

    assert response.location == "East Entrance"
    assert response.title == "Red backpack"
    assert response.description == "Contains a notebook"
    assert response.category == "accessories"
    assert response.date_lost == date(2026, 10, 25)
    assert response.updated_at > OLD_UPDATED_AT


def test_description_can_be_cleared():
    update = LostItemUpdate(description=None)

    assert update.model_dump(exclude_unset=True) == {"description": None}
    assert LostItemUpdate(description="  ").description is None


def test_nonexistent_item_returns_404(database_session):
    owner = create_user(database_session, "alice", "alice@example.com")

    with pytest.raises(HTTPException) as error:
        items.update_lost_item(
            9999,
            LostItemUpdate(title="Updated item"),
            owner,
            database_session,
        )

    assert error.value.status_code == status.HTTP_404_NOT_FOUND
    assert error.value.detail == "Lost item not found"


def test_different_authenticated_user_is_forbidden_and_item_is_unchanged(
    database_session,
):
    owner = create_user(database_session, "alice", "alice@example.com")
    other_user = create_user(database_session, "bob", "bob@example.com")
    lost_item = create_item(database_session, owner)

    with pytest.raises(HTTPException) as error:
        items.update_lost_item(
            lost_item.id,
            LostItemUpdate(title="Hijacked title"),
            other_user,
            database_session,
        )

    assert error.value.status_code == status.HTTP_403_FORBIDDEN
    assert error.value.detail == "You do not have permission to update this item"
    database_session.refresh(lost_item)
    assert lost_item.title == "Red backpack"
    assert lost_item.user_id == owner.id


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": None},
        {"category": None},
        {"location": None},
        {"date_lost": None},
        {"title": "  "},
        {"title": "x" * 201},
        {"category": "x" * 51},
        {"location": "x" * 256},
        {"date_lost": "not-a-date"},
        {"id": 9},
        {"user_id": 9},
        {"image_path": "attacker/path"},
        {"status": "closed"},
        {"created_at": "2026-01-01T00:00:00"},
        {"updated_at": "2026-01-01T00:00:00"},
    ],
)
def test_update_schema_rejects_empty_invalid_or_protected_fields(payload):
    with pytest.raises(ValidationError):
        LostItemUpdate.model_validate(payload)


def test_update_route_requires_auth_and_uses_safe_response_schema():
    route = next(
        route
        for route in items.router.routes
        if route.path == "/{item_id}" and "PATCH" in route.methods
    )

    assert route.response_model is LostItemResponse
    assert any(
        dependency.call is dependencies.get_current_user
        for dependency in route.dependant.dependencies
    )
    assert "patch" in app.openapi()["paths"]["/api/items/{item_id}"]


def test_missing_and_invalid_jwt_are_rejected(monkeypatch):
    configured = Settings(
        JWT_SECRET_KEY=TEST_SECRET,
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
    )
    monkeypatch.setattr(dependencies, "settings", configured)

    for credentials in (
        None,
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt"),
    ):
        with pytest.raises(HTTPException) as error:
            dependencies.get_current_user(credentials, Mock())
        assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert error.value.headers == {"WWW-Authenticate": "Bearer"}
