from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.user import UserProfileUpdate, UserResponse

router = APIRouter()


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    updates: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    values = updates.model_dump(exclude_unset=True)
    if "username" in values:
        values["username"] = values["username"].strip()
    if "email" in values:
        values["email"] = str(values["email"]).strip().casefold()
    values = {
        field: value
        for field, value in values.items()
        if value != getattr(current_user, field)
    }
    if not values:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No profile changes provided",
        )

    try:
        username = values.get("username")
        if username is not None and username != current_user.username:
            existing_id = db.scalar(
                select(User.id).where(
                    User.username == username,
                    User.id != current_user.id,
                )
            )
            if existing_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username already registered",
                )

        email = values.get("email")
        if email is not None and email != current_user.email:
            existing_id = db.scalar(
                select(User.id).where(
                    User.email == email,
                    User.id != current_user.id,
                )
            )
            if existing_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                )

        for field, value in values.items():
            setattr(current_user, field, value)
        db.commit()
        db.refresh(current_user)
    except HTTPException:
        raise
    except IntegrityError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        ) from None
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Profile update service unavailable",
        ) from None

    return UserResponse.model_validate(current_user)
