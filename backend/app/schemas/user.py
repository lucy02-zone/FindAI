from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Username = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=50),
]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
LoginPassword = Annotated[str, StringConstraints(min_length=1, max_length=128)]
EmailAddress = Annotated[EmailStr, Field(max_length=255)]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    email: EmailAddress
    password: Password


class UserLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailAddress
    password: LoginPassword


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    is_active: bool
    created_at: datetime
