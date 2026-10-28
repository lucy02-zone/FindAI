from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import dependencies, items
from app.core.config import Settings
from app.db.base import Base
from app.main import app
from app.models import LostItem, User

TEST_SECRET = "test-only-signing-secret-with-at-least-32-bytes"


@pytest.fixture
def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def add_owner_and_item(db):
    owner = User(
        username="alice",
        email="alice@example.com",
        hashed_password="private-test-hash",
        is_active=True,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    item = LostItem(
        title="Red backpack",
        description="Contains a notebook",
        category="accessories",
        location="Central Library",
        date_lost=date(2026, 10, 25),
        image_path="uploads/red-backpack.jpg",
        status="open",
        user_id=owner.id,
        created_at=datetime(2026, 10, 26, 11, 30),
        updated_at=datetime(2026, 10, 26, 11, 30),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return owner, item


def test_owner_can_delete_item_with_empty_204_and_user_preserved(database_session):
    owner, item = add_owner_and_item(database_session)
    item_id = item.id

    response = items.delete_lost_item(item_id, owner, database_session)

    assert isinstance(response, Response)
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.body == b""
    assert database_session.get(LostItem, item_id) is None
    assert database_session.get(User, owner.id) is owner


def test_delete_nonexistent_item_returns_404(database_session):
    owner, _ = add_owner_and_item(database_session)

    with pytest.raises(HTTPException) as error:
        items.delete_lost_item(9999, owner, database_session)

    assert error.value.status_code == status.HTTP_404_NOT_FOUND
    assert error.value.detail == "Lost item not found"


@pytest.mark.parametrize("item_id", [0, -1])
def test_delete_path_id_must_be_positive(item_id):
    with pytest.raises(ValidationError):
        TypeAdapter(items.PositiveItemId).validate_python(item_id)


def test_another_user_cannot_delete_item(database_session):
    owner, item = add_owner_and_item(database_session)
    other_user = User(
        username="bob",
        email="bob@example.com",
        hashed_password="another-private-hash",
        is_active=True,
    )
    database_session.add(other_user)
    database_session.commit()
    database_session.refresh(other_user)

    with pytest.raises(HTTPException) as error:
        items.delete_lost_item(item.id, other_user, database_session)

    assert error.value.status_code == status.HTTP_403_FORBIDDEN
    assert error.value.detail == "You do not have permission to delete this item"
    assert database_session.get(LostItem, item.id) is item
    assert database_session.get(User, owner.id) is owner


def test_delete_route_requires_auth_and_has_no_client_controlled_body():
    route = next(
        route
        for route in items.router.routes
        if route.path == "/{item_id}" and "DELETE" in route.methods
    )
    app_route = app.openapi()["paths"]["/api/items/{item_id}"]["delete"]

    assert route.status_code == status.HTTP_204_NO_CONTENT
    assert route.response_class is Response
    assert route.response_model is None
    assert route.body_field is None
    assert any(
        dependency.call is dependencies.get_current_user
        for dependency in route.dependant.dependencies
    )
    assert "requestBody" not in app_route


def test_missing_and_invalid_jwt_are_rejected(monkeypatch):
    configured = Settings(
        JWT_SECRET_KEY=TEST_SECRET,
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
    )
    monkeypatch.setattr(dependencies, "settings", configured)
    credentials = (
        None,
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt"),
    )

    for bearer in credentials:
        with pytest.raises(HTTPException) as error:
            dependencies.get_current_user(bearer, Mock())
        assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert error.value.headers == {"WWW-Authenticate": "Bearer"}


def test_delete_database_error_rolls_back_and_returns_generic_response():
    owner = SimpleNamespace(id=17, is_active=True)
    item = SimpleNamespace(id=8, user_id=owner.id)
    db = Mock()
    db.get.return_value = item
    db.commit.side_effect = SQLAlchemyError("private database details")

    with pytest.raises(HTTPException) as error:
        items.delete_lost_item(8, owner, db)

    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert error.value.detail == "Lost item could not be deleted"
    assert "private" not in error.value.detail
    db.delete.assert_called_once_with(item)
    db.rollback.assert_called_once_with()
