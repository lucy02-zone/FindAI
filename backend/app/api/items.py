import logging
import os
import uuid
import warnings
from pathlib import Path as FilesystemPath
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import BACKEND_DIR, settings
from app.db.session import get_db
from app.models import LostItem, User
from app.schemas.item import (
    LostItemCreate,
    LostItemListQuery,
    LostItemImageUploadResponse,
    LostItemResponse,
    LostItemUpdate,
)

router = APIRouter()
PositiveItemId = Annotated[int, Path(gt=0)]
logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}
UPLOAD_CHUNK_SIZE = 64 * 1024


def _upload_root() -> FilesystemPath:
    configured = FilesystemPath(settings.UPLOAD_DIR)
    root = configured if configured.is_absolute() else BACKEND_DIR / configured
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _remove_owned_upload(root: FilesystemPath, relative_path: str | None) -> None:
    """Remove only a generated file directly inside the configured upload root."""
    if not relative_path:
        return
    candidate = FilesystemPath(relative_path)
    if (
        candidate.is_absolute()
        or len(candidate.parts) != 2
        or candidate.parts[0] != "uploads"
    ):
        return
    filename = candidate.parts[1]
    if not filename or FilesystemPath(filename).name != filename:
        return
    path = root / filename
    try:
        if path.parent.resolve() == root and not path.is_symlink() and path.is_file():
            path.unlink()
    except OSError:
        logger.warning("Unable to remove replaced item image")


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


@router.get("", response_model=list[LostItemResponse])
def list_lost_items(
    filters: Annotated[LostItemListQuery, Depends()],
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LostItemResponse]:
    statement = select(LostItem)
    if filters.category is not None:
        statement = statement.where(LostItem.category == filters.category)
    if filters.status is not None:
        statement = statement.where(LostItem.status == filters.status)
    statement = statement.order_by(
        LostItem.created_at.desc(),
        LostItem.id.desc(),
    )
    statement = statement.offset(filters.skip).limit(filters.limit)

    try:
        lost_items = db.scalars(statement).all()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lost items are temporarily unavailable",
        ) from None

    return [LostItemResponse.model_validate(item) for item in lost_items]


@router.get("/{item_id}", response_model=LostItemResponse)
def get_lost_item(
    item_id: PositiveItemId,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LostItemResponse:
    try:
        lost_item = db.get(LostItem, item_id)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lost item is temporarily unavailable",
        ) from None

    if lost_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lost item not found",
        )

    return LostItemResponse.model_validate(lost_item)


@router.patch("/{item_id}", response_model=LostItemResponse)
def update_lost_item(
    item_id: PositiveItemId,
    updates: LostItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LostItemResponse:
    try:
        lost_item = db.get(LostItem, item_id)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lost item is temporarily unavailable",
        ) from None

    if lost_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lost item not found",
        )
    if lost_item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this item",
        )

    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(lost_item, field, value)

    try:
        db.commit()
        db.refresh(lost_item)
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lost item could not be updated",
        ) from None

    return LostItemResponse.model_validate(lost_item)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_lost_item(
    item_id: PositiveItemId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        lost_item = db.get(LostItem, item_id)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lost item is temporarily unavailable",
        ) from None

    if lost_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lost item not found",
        )
    if lost_item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this item",
        )

    try:
        db.delete(lost_item)
        db.commit()
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lost item could not be deleted",
        ) from None

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{item_id}/image",
    response_model=LostItemImageUploadResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_lost_item_image(
    item_id: PositiveItemId,
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LostItemImageUploadResponse:
    try:
        lost_item = db.get(LostItem, item_id)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lost item is temporarily unavailable",
        ) from None

    if lost_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lost item not found",
        )
    if lost_item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this item",
        )

    if settings.UPLOAD_MAX_SIZE_MB < 1:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image upload is not configured correctly",
        )
    max_bytes = settings.UPLOAD_MAX_SIZE_MB * 1024 * 1024
    try:
        root = _upload_root()
        temporary_path = root / f".{uuid.uuid4().hex}.upload"
        total = 0
        with temporary_path.open("xb") as target:
            while chunk := await image.read(UPLOAD_CHUNK_SIZE):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Image exceeds the maximum allowed size",
                    )
                target.write(chunk)

        if total == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image file is empty",
            )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(temporary_path) as uploaded_image:
                    image_type = ALLOWED_IMAGE_TYPES.get(uploaded_image.format or "")
                    if image_type is None:
                        raise HTTPException(
                            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="Only JPEG, PNG, and WebP images are supported",
                        )
                    uploaded_image.verify()
        except HTTPException:
            raise
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is not a valid image",
            ) from None

        _, extension = image_type
        filename = f"{uuid.uuid4().hex}{extension}"
        final_path = root / filename
        # Hard-linking from our exclusive temporary file guarantees no overwrite.
        os.link(temporary_path, final_path)
        os.chmod(final_path, 0o600)
        temporary_path.unlink()
        previous_image_path = lost_item.image_path
        stored_path = f"uploads/{filename}"
        lost_item.image_path = stored_path
        try:
            db.commit()
        except SQLAlchemyError:
            try:
                db.rollback()
            except SQLAlchemyError:
                pass
            _remove_owned_upload(root, stored_path)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Image could not be saved",
            ) from None

        _remove_owned_upload(root, previous_image_path)
        return LostItemImageUploadResponse(image_path=stored_path)
    except HTTPException:
        if "temporary_path" in locals():
            temporary_path.unlink(missing_ok=True)
        if "final_path" in locals():
            final_path.unlink(missing_ok=True)
        raise
    except OSError:
        if "temporary_path" in locals():
            temporary_path.unlink(missing_ok=True)
        if "final_path" in locals():
            final_path.unlink(missing_ok=True)
        logger.exception("Lost item image storage operation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image could not be stored",
        ) from None
    finally:
        await image.close()
