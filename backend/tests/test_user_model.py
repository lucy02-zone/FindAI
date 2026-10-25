from sqlalchemy import Boolean, DateTime, Integer, String

from app.db.base import Base
from app.models import User


def test_user_table_name_and_columns() -> None:
    table = User.__table__

    assert table.name == "users"
    assert set(table.columns.keys()) == {
        "id",
        "username",
        "email",
        "hashed_password",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert table.metadata is Base.metadata


def test_user_primary_key_and_column_types() -> None:
    table = User.__table__

    assert [column.name for column in table.primary_key.columns] == ["id"]
    assert isinstance(table.c.id.type, Integer)
    assert isinstance(table.c.username.type, String)
    assert table.c.username.type.length == 50
    assert isinstance(table.c.email.type, String)
    assert table.c.email.type.length == 255
    assert isinstance(table.c.hashed_password.type, String)
    assert table.c.hashed_password.type.length == 255
    assert isinstance(table.c.is_active.type, Boolean)
    assert isinstance(table.c.created_at.type, DateTime)
    assert isinstance(table.c.updated_at.type, DateTime)


def test_username_and_email_are_unique_and_indexed() -> None:
    table = User.__table__

    for name in ("username", "email"):
        column = table.c[name]
        assert column.unique is True
        assert column.index is True
        assert any(index.unique and column in index.columns for index in table.indexes)


def test_required_user_fields_are_non_nullable() -> None:
    table = User.__table__

    for name in ("username", "email", "hashed_password", "is_active", "created_at", "updated_at"):
        assert table.c[name].nullable is False


def test_timestamp_defaults_are_server_side_and_updated_at_changes_on_update() -> None:
    table = User.__table__

    assert table.c.created_at.server_default is not None
    assert table.c.updated_at.server_default is not None
    assert table.c.updated_at.onupdate is not None
