from datetime import date, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

ItemTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
ItemCategory = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
]
ItemLocation = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
ItemStatus = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20),
]


class LostItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: ItemTitle
    description: str | None = None
    category: ItemCategory
    location: ItemLocation
    date_lost: date

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class LostItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: ItemTitle | None = None
    description: str | None = None
    category: ItemCategory | None = None
    location: ItemLocation | None = None
    date_lost: date | None = None

    @field_validator("title", "category", "location", "date_lost", mode="before")
    @classmethod
    def reject_null_required_updates(cls, value):
        if value is None:
            raise ValueError("This item field cannot be null")
        return value

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one item field must be provided")
        return self


class LostItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    category: str
    location: str
    date_lost: date
    status: str
    user_id: int
    created_at: datetime
    updated_at: datetime


class LostItemListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skip: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    category: ItemCategory | None = None
    status: ItemStatus | None = None
