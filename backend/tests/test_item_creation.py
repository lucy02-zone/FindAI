from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import dependencies, items
from app.core.config import Settings
from app.db.base import Base
from app.models import LostItem, User
from app.schemas.item import LostItemCreate, LostItemResponse
from app.main import app

TEST_SECRET = "test-only-signing-secret-with-at-least-32-bytes"


@pytest.fixture
def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_create_lost_item_persists_with_authenticated_owner(database_session):
    owner = User(
        username="alice",
        email="alice@example.com",
        hashed_password="unused-test-hash",
        is_active=True,
    )
    database_session.add(owner)
    database_session.commit()
    database_session.refresh(owner)
    payload = LostItemCreate(
        title="  Red backpack  ",
        description="  Contains a notebook.  ",
        category="  accessories  ",
        location="  Central Library  ",
        date_lost=date(2026, 10, 25),
    )

    response = items.create_lost_item(payload, owner, database_session)

    assert isinstance(response, LostItemResponse)
    assert response.id > 0
    assert response.title == "Red backpack"
    assert response.description == "Contains a notebook."
    assert response.category == "accessories"
    assert response.location == "Central Library"
    assert response.date_lost == date(2026, 10, 25)
    assert response.status == "open"
    assert response.user_id == owner.id
    assert response.created_at is not None
    assert response.updated_at is not None
    persisted = database_session.get(LostItem, response.id)
    assert persisted is not None
    assert persisted.user_id == owner.id
    assert persisted.image_path is None


def test_create_endpoint_uses_authenticated_user_and_returns_created_status():
    route = next(route for route in items.router.routes if route.path == "")
    application_route = next(route for route in app.routes if route.path == "/api/items")

    assert "POST" in route.methods
    assert route.status_code == status.HTTP_201_CREATED
    assert "POST" in application_route.methods
    assert route.response_model is LostItemResponse
    assert any(
        dependency.call is dependencies.get_current_user
        for dependency in route.dependant.dependencies
    )


@pytest.mark.parametrize(
    "data",
    [
        {"description": "details", "category": "other", "location": "Park", "date_lost": "2026-10-25"},
        {"title": "Bag", "description": None, "location": "Park", "date_lost": "2026-10-25"},
        {"title": "Bag", "description": None, "category": "other", "date_lost": "2026-10-25"},
        {"title": "Bag", "description": None, "category": "other", "location": "Park"},
    ],
    ids=["missing-title", "missing-category", "missing-location", "missing-date"],
)
def test_create_schema_rejects_missing_required_fields(data):
    with pytest.raises(ValidationError):
        LostItemCreate.model_validate(data)


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "  "},
        {"location": "  "},
        {"title": "x" * 201},
        {"category": "x" * 51},
        {"location": "x" * 256},
        {"date_lost": "not-a-date"},
    ],
)
def test_create_schema_rejects_invalid_fields(overrides):
    data = {
        "title": "Backpack",
        "description": None,
        "category": "other",
        "location": "Park",
        "date_lost": "2026-10-25",
        **overrides,
    }

    with pytest.raises(ValidationError):
        LostItemCreate.model_validate(data)


@pytest.mark.parametrize("field", ["id", "user_id", "status", "image_path"])
def test_create_schema_rejects_client_controlled_fields(field):
    data = {
        "title": "Backpack",
        "category": "other",
        "location": "Park",
        "date_lost": "2026-10-25",
        field: 123 if field in {"id", "user_id"} else "attacker-value",
    }

    with pytest.raises(ValidationError):
        LostItemCreate.model_validate(data)


def test_blank_description_is_stored_as_null():
    payload = LostItemCreate(
        title="Backpack",
        description="   ",
        category="other",
        location="Park",
        date_lost=date(2026, 10, 25),
    )

    assert payload.description is None


def test_create_database_error_rolls_back_without_leaking_details():
    db = Mock()
    db.commit.side_effect = SQLAlchemyError("private database connection detail")
    owner = SimpleNamespace(id=17, is_active=True)
    payload = LostItemCreate(
        title="Backpack",
        category="other",
        location="Park",
        date_lost=date(2026, 10, 25),
    )

    with pytest.raises(HTTPException) as error:
        items.create_lost_item(payload, owner, db)

    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert error.value.detail == "Lost item could not be created"
    assert "private" not in error.value.detail
    persisted_item = db.add.call_args.args[0]
    assert persisted_item.user_id == owner.id
    assert persisted_item.status is None  # SQLAlchemy applies the model default at insert time.
    db.rollback.assert_called_once_with()


def test_missing_or_invalid_authentication_is_rejected(monkeypatch):
    configured = Settings(
        JWT_SECRET_KEY=TEST_SECRET,
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
    )
    monkeypatch.setattr(dependencies, "settings", configured)

    for credentials in (None,):
        with pytest.raises(HTTPException) as error:
            dependencies.get_current_user(credentials, Mock())
        assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert error.value.headers == {"WWW-Authenticate": "Bearer"}

    invalid = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt")
    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(invalid, Mock())
    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}


def test_deactivated_user_is_rejected_before_item_creation(monkeypatch):
    configured = Settings(
        JWT_SECRET_KEY=TEST_SECRET,
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
    )
    monkeypatch.setattr(dependencies, "settings", configured)
    token = jwt.encode({"sub": "17", "exp": 4_102_444_800}, TEST_SECRET, algorithm="HS256")
    bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = Mock()
    db.scalar.return_value = SimpleNamespace(id=17, is_active=False)

    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(bearer, db)

    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
