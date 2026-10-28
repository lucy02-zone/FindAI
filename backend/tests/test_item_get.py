from datetime import date, datetime
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api import dependencies, items
from app.db.base import Base
from app.main import app
from app.models import LostItem, User
from app.schemas.item import LostItemResponse


@pytest.fixture
def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def add_report(db):
    owner = User(
        username="alice",
        email="alice@example.com",
        hashed_password="private-hash",
        is_active=True,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    report = LostItem(
        title="Red backpack",
        description="Contains a notebook",
        category="accessories",
        location="Central Library",
        date_lost=date(2026, 10, 25),
        status="open",
        user_id=owner.id,
        created_at=datetime(2026, 10, 26, 11, 30, 0),
        updated_at=datetime(2026, 10, 26, 11, 30, 0),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return owner, report


def test_get_item_returns_safe_fields_for_authenticated_user(database_session):
    owner, report = add_report(database_session)

    response = items.get_lost_item(report.id, owner, database_session)

    assert isinstance(response, LostItemResponse)
    assert response.model_dump() == {
        "id": report.id,
        "title": "Red backpack",
        "description": "Contains a notebook",
        "category": "accessories",
        "location": "Central Library",
        "date_lost": date(2026, 10, 25),
        "status": "open",
        "user_id": owner.id,
        "created_at": datetime(2026, 10, 26, 11, 30, 0),
        "updated_at": datetime(2026, 10, 26, 11, 30, 0),
    }
    assert "image_path" not in response.model_dump()
    assert "hashed_password" not in response.model_dump()


def test_get_item_returns_404_for_unknown_id(database_session):
    owner, _ = add_report(database_session)

    with pytest.raises(HTTPException) as error:
        items.get_lost_item(9999, owner, database_session)

    assert error.value.status_code == status.HTTP_404_NOT_FOUND
    assert error.value.detail == "Lost item not found"


@pytest.mark.parametrize("item_id", [0, -1])
def test_item_id_path_constraint_requires_a_positive_integer(item_id):
    with pytest.raises(ValidationError):
        TypeAdapter(items.PositiveItemId).validate_python(item_id)


def test_item_id_path_parameter_is_documented_as_positive_integer():
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/items/{item_id}"
        and "GET" in getattr(route, "methods", set())
    )
    item_parameter = next(
        parameter
        for parameter in app.openapi()["paths"]["/api/items/{item_id}"]["get"]["parameters"]
        if parameter["name"] == "item_id"
    )

    assert route.response_model is LostItemResponse
    assert item_parameter["in"] == "path"
    assert item_parameter["required"] is True
    assert item_parameter["schema"]["exclusiveMinimum"] == 0


def test_get_item_route_requires_existing_auth_dependency():
    route = next(
        route
        for route in items.router.routes
        if route.path == "/{item_id}" and "GET" in route.methods
    )

    assert any(
        dependency.call is dependencies.get_current_user
        for dependency in route.dependant.dependencies
    )


def test_missing_authentication_is_rejected_before_item_lookup():
    db = Mock()

    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(None, db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
    db.get.assert_not_called()
