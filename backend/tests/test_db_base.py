from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def test_base_supports_declarative_models() -> None:
    class TestModel(Base):
        __tablename__ = "test_declarative_base_model"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)

    assert issubclass(TestModel, Base)
    assert "test_declarative_base_model" in Base.metadata.tables
