import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.user import (
    PasswordChangeRequest,
    PasswordChangeResponse,
    AccountDeactivationRequest,
    AccountDeactivationResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _log_login_failure(stage: str, error: Exception) -> None:
    """Log stack locations and exception type without logging exception values."""
    frames = traceback.extract_tb(error.__traceback__)
    stack = "\n".join(
        f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
        for frame in frames
    )
    logger.error(
        "Login %s failed with %s; traceback follows:\n%s",
        stage,
        type(error).__name__,
        stack,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> UserResponse:
    email = str(user_data.email).strip().casefold()
    username = user_data.username.strip()

    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already registered",
        )

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(user_data.password),
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already registered",
        ) from None

    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login_user(
    credentials: UserLogin,
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = str(credentials.email).strip().casefold()
    try:
        user = db.scalar(select(User).where(User.email == email))
    except SQLAlchemyError as error:
        _log_login_failure("database lookup", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from None
    except Exception as error:
        _log_login_failure("database lookup", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from None

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        password_valid = verify_password(credentials.password, user.hashed_password)
    except Exception as error:
        _log_login_failure("password verification", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from None

    if not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token = create_access_token(str(user.id))
    except Exception as error:
        _log_login_failure("token creation", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from None
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def read_current_user(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post(
    "/change-password",
    response_model=PasswordChangeResponse,
)
def change_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PasswordChangeResponse:
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if password_data.current_password == password_data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from the current password",
        )

    current_user.hashed_password = hash_password(password_data.new_password)
    try:
        db.commit()
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password change service unavailable",
        ) from None

    return PasswordChangeResponse()


@router.post(
    "/deactivate",
    response_model=AccountDeactivationResponse,
)
def deactivate_account(
    request: AccountDeactivationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountDeactivationResponse:
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.is_active = False
    try:
        db.commit()
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account deactivation service unavailable",
        ) from None

    return AccountDeactivationResponse()
