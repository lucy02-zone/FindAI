import asyncio
from datetime import date

from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import dependencies, items
from app.api.dependencies import bearer_scheme
from app.api.auth import login_user
from app.core import security
from app.core.config import Settings
from app.db.base import Base
from app.models import LostItem, User
from app.schemas.item import LostItemCreate
from app.schemas.user import UserLogin
from app.main import app


def test_fresh_login_token_authorizes_protected_item_creation(monkeypatch):
    configured = Settings(
        JWT_SECRET_KEY="test-only-signing-secret-with-at-least-32-bytes",
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
    )
    monkeypatch.setattr(security, "settings", configured)
    monkeypatch.setattr(dependencies, "settings", configured)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    try:
        with Session(engine) as db:
            owner = User(
                username="alice",
                email="alice@example.com",
                hashed_password=security.hash_password(
                    "correct horse battery staple"
                ),
                is_active=True,
            )
            db.add(owner)
            db.commit()
            expected_owner_id = owner.id

            login_response = login_user(
                UserLogin(
                    email="alice@example.com",
                    password="correct horse battery staple",
                ),
                db,
            )
            login_route = next(
                route for route in app.routes if getattr(route, "path", None) == "/api/auth/login"
            )
            assert login_route.status_code in (None, 200)
            authorization_header = f"Bearer {login_response.access_token}"
            request = Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/items",
                    "headers": [(b"authorization", authorization_header.encode())],
                }
            )
            credentials = asyncio.run(bearer_scheme(request))

            assert credentials is not None
            assert credentials.scheme == "Bearer"
            assert credentials.credentials == login_response.access_token

            current_user = dependencies.get_current_user(credentials, db)
            response = items.create_lost_item(
                LostItemCreate(
                    title="Red backpack",
                    category="accessories",
                    location="Central Library",
                    date_lost=date(2026, 10, 25),
                ),
                current_user,
                db,
            )

            assert response.user_id == expected_owner_id
            assert response.status == "open"
            assert db.get(LostItem, response.id) is not None
    finally:
        engine.dispose()


def test_swagger_openapi_declares_http_bearer_for_item_creation():
    schema = app.openapi()

    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert {"HTTPBearer": []} in schema["paths"]["/api/items"]["post"]["security"]
