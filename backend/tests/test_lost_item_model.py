from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text

from app.db.base import Base
from app.models import LostItem, User


def test_lost_item_table_columns_and_shared_metadata():
    table = LostItem.__table__

    assert table.name == "lost_items"
    assert table.metadata is Base.metadata
    assert set(table.columns.keys()) == {
        "id",
        "title",
        "description",
        "category",
        "location",
        "date_lost",
        "image_path",
        "status",
        "user_id",
        "created_at",
        "updated_at",
    }
    assert isinstance(table.c.id.type, Integer)
    assert table.c.id.primary_key
    assert isinstance(table.c.title.type, String)
    assert table.c.title.type.length == 200
    assert isinstance(table.c.description.type, Text)
    assert isinstance(table.c.category.type, String)
    assert table.c.category.type.length == 50
    assert isinstance(table.c.location.type, String)
    assert table.c.location.type.length == 255
    assert isinstance(table.c.date_lost.type, Date)
    assert isinstance(table.c.image_path.type, String)
    assert table.c.image_path.type.length == 512
    assert isinstance(table.c.status.type, String)
    assert table.c.status.type.length == 20
    assert table.c.status.default.arg == "open"
    assert str(table.c.status.server_default.arg) == "'open'"
    assert isinstance(table.c.created_at.type, DateTime)
    assert isinstance(table.c.updated_at.type, DateTime)


def test_lost_item_required_and_optional_fields():
    table = LostItem.__table__

    for name in (
        "id",
        "title",
        "category",
        "location",
        "date_lost",
        "status",
        "user_id",
        "created_at",
        "updated_at",
    ):
        assert table.c[name].nullable is False
    assert table.c.description.nullable is True
    assert table.c.image_path.nullable is True


def test_lost_item_user_foreign_key_and_relationships():
    table = LostItem.__table__
    foreign_keys = list(table.c.user_id.foreign_keys)

    assert len(foreign_keys) == 1
    foreign_key = foreign_keys[0]
    assert isinstance(foreign_key, ForeignKey)
    assert foreign_key.target_fullname == "users.id"
    assert foreign_key.constraint.name == "fk_lost_items_user_id_users"
    assert LostItem.user.property.back_populates == "lost_items"
    assert User.lost_items.property.back_populates == "user"


def test_user_and_lost_item_use_same_sqlalchemy_base():
    assert User.__table__.metadata is LostItem.__table__.metadata
