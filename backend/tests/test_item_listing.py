from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import dependencies, items
from app.db.base import Base
from app.main import app
from app.models import LostItem, User
from app.schemas.item import LostItemListQuery, LostItemResponse


@pytest.fixture
def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def create_owner(db):
    owner = User(
        username="alice",
        email="alice@example.com",
        hashed_password="unused-test-hash",
        is_active=True,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner


def add_item(db, owner, *, title, category, status, created_at):
    item = LostItem(
        title=title,
        description=f"Details for {title}",
        category=category,
        location="Central Library",
        date_lost=date(2026, 10, 25),
        status=status,
        user_id=owner.id,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_listing_returns_safe_results_newest_first(database_session):
    owner = create_owner(database_session)
    oldest = add_item(
        database_session,
        owner,
        title="Old bag",
        category="accessories",
        status="open",
        created_at=datetime(2026, 10, 1, 10),
    )
    older_tie = add_item(
        database_session,
        owner,
        title="Earlier tied bag",
        category="accessories",
        status="open",
        created_at=datetime(2026, 10, 2, 10),
    )
    newest_tie = add_item(
        database_session,
        owner,
        title="Later tied bag",
        category="electronics",
        status="closed",
        created_at=datetime(2026, 10, 2, 10),
    )

    results = items.list_lost_items(
        LostItemListQuery(),
        owner,
        database_session,
    )

    assert [item.id for item in results] == [newest_tie.id, older_tie.id, oldest.id]
    assert all(isinstance(item, LostItemResponse) for item in results)
    first = results[0].model_dump()
    assert set(first) == {
        "id",
        "title",
        "description",
        "category",
        "location",
        "date_lost",
        "status",
        "user_id",
        "created_at",
        "updated_at",
    }
    assert "image_path" not in first
    assert "hashed_password" not in first


def test_listing_returns_empty_list_when_no_reports_match(database_session):
    owner = create_owner(database_session)

    results = items.list_lost_items(
        LostItemListQuery(),
        owner,
        database_session,
    )

    assert results == []


def test_listing_applies_skip_and_limit(database_session):
    owner = create_owner(database_session)
    for index in range(3):
        add_item(
            database_session,
            owner,
            title=f"Item {index}",
            category="other",
            status="open",
            created_at=datetime(2026, 10, 1 + index, 10),
        )

    results = items.list_lost_items(
        LostItemListQuery(skip=1, limit=1),
        owner,
        database_session,
    )

    assert len(results) == 1
    assert results[0].title == "Item 1"


def test_listing_filters_by_category_and_status(database_session):
    owner = create_owner(database_session)
    expected = add_item(
        database_session,
        owner,
        title="Electronics closed",
        category="electronics",
        status="closed",
        created_at=datetime(2026, 10, 3, 10),
    )
    add_item(
        database_session,
        owner,
        title="Electronics open",
        category="electronics",
        status="open",
        created_at=datetime(2026, 10, 4, 10),
    )
    add_item(
        database_session,
        owner,
        title="Clothing closed",
        category="clothing",
        status="closed",
        created_at=datetime(2026, 10, 5, 10),
    )

    results = items.list_lost_items(
        LostItemListQuery(category=" electronics ", status=" closed "),
        owner,
        database_session,
    )

    assert [item.id for item in results] == [expected.id]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("skip", -1),
        ("limit", 0),
        ("limit", 101),
        ("category", " "),
        ("category", "x" * 51),
        ("status", " "),
        ("status", "x" * 21),
        ("unexpected", "value"),
    ],
)
def test_listing_query_rejects_invalid_parameters(field, value):
    with pytest.raises(ValidationError):
        LostItemListQuery.model_validate({field: value})


def test_listing_endpoint_is_protected_and_registered_under_items():
    router_route = next(
        route
        for route in items.router.routes
        if route.path == "" and "GET" in route.methods
    )
    app_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/items"
        and "GET" in getattr(route, "methods", set())
    )

    assert "GET" in router_route.methods
    assert app_route.response_model == list[LostItemResponse]
    assert any(
        dependency.call is dependencies.get_current_user
        for dependency in router_route.dependant.dependencies
    )
    assert [
        parameter["name"]
        for parameter in app.openapi()["paths"]["/api/items"]["get"]["parameters"]
    ] == ["skip", "limit", "category", "status"]


def test_missing_authentication_is_rejected_for_listing():
    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(None, Mock())

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}


def test_listing_database_errors_return_generic_unavailable_response():
    db = Mock()
    db.scalars.side_effect = SQLAlchemyError("private database details")
    active_user = SimpleNamespace(id=10, is_active=True)

    with pytest.raises(HTTPException) as error:
        items.list_lost_items(LostItemListQuery(), active_user, db)

    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert error.value.detail == "Lost items are temporarily unavailable"
    assert "private" not in error.value.detail
