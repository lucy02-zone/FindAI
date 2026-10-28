from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

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
