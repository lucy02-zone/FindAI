from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models import LostItem, User
from app.schemas.item import LostItemCreate, LostItemResponse

router = APIRouter()


@router.post("", response_model=LostItemResponse, status_code=status.HTTP_201_CREATED)
def create_lost_item(
    item_data: LostItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LostItemResponse:
    lost_item = LostItem(
        title=item_data.title,
        description=item_data.description,
        category=item_data.category,
        location=item_data.location,
        date_lost=item_data.date_lost,
        user_id=current_user.id,
    )

    try:
        db.add(lost_item)
        db.commit()
        db.refresh(lost_item)
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lost item could not be created",
        ) from None

    return LostItemResponse.model_validate(lost_item)
