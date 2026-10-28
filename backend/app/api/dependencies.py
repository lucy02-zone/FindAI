from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Validate a bearer access token and load its user from the database."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    if not settings.JWT_SECRET_KEY:
        raise unauthorized

    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.isdecimal():
            raise unauthorized
        user_id = int(subject)
        if user_id <= 0 or user_id > 2_147_483_647:
            raise unauthorized
    except (jwt.PyJWTError, ValueError, TypeError):
        raise unauthorized from None

    try:
        user = db.scalar(select(User).where(User.id == user_id))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from None

    if user is None or not user.is_active:
        raise unauthorized
    return user
