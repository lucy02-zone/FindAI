import logging
import traceback
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
logger = logging.getLogger(__name__)


def _log_auth_failure(stage: str, error: Exception | None = None) -> None:
    """Log safe auth diagnostics without headers, exception values, or claims."""
    if error is None:
        logger.warning("Bearer authentication rejected at %s", stage)
        return

    frames = traceback.extract_tb(error.__traceback__)
    stack = "\n".join(
        f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
        for frame in frames
    )
    logger.error(
        "Bearer authentication failed at %s with %s; traceback follows:\n%s",
        stage,
        type(error).__name__,
        stack,
    )


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
        _log_auth_failure("Authorization header parsing")
        raise unauthorized
    token = credentials.credentials.strip()
    if token.lower().startswith("bearer "):
        logger.warning(
            "Authorization credential contained a repeated Bearer scheme; normalizing before JWT validation"
        )
        token = token[7:].strip()
    if not settings.JWT_SECRET_KEY:
        logger.error("Bearer authentication unavailable: JWT signing key is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.isdecimal():
            raise unauthorized
        user_id = int(subject)
        if user_id <= 0 or user_id > 2_147_483_647:
            raise unauthorized
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        _log_auth_failure("JWT signature or claims validation", error)
        raise unauthorized from None

    try:
        user = db.scalar(select(User).where(User.id == user_id))
    except SQLAlchemyError as error:
        _log_auth_failure("current-user database lookup", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from None
    except Exception as error:
        _log_auth_failure("current-user database lookup", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from None

    if user is None:
        _log_auth_failure("current-user lookup returned no user")
        raise unauthorized
    if not user.is_active:
        _log_auth_failure("account status check")
        raise unauthorized
    return user
