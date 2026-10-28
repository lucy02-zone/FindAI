from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

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


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: LoginPassword
    new_password: Password


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username | None = None
    email: EmailAddress | None = None

    @field_validator("username", "email", mode="before")
    @classmethod
    def reject_null_updates(cls, value):
        if value is None:
            raise ValueError("A profile field cannot be null")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one profile field must be provided")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordChangeResponse(BaseModel):
    message: str = "Password updated successfully"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    is_active: bool
    created_at: datetime
