import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError

from app.api import dependencies, items
from app.core.config import Settings
from app.main import app


@pytest.fixture
def setup_upload(monkeypatch, tmp_path):
    configured = Settings(UPLOAD_DIR=str(tmp_path / "uploads"), UPLOAD_MAX_SIZE_MB=5)
    monkeypatch.setattr(items, "settings", configured)
    owner = SimpleNamespace(id=23, is_active=True)
    item = SimpleNamespace(id=7, user_id=owner.id, image_path=None)
    db = Mock()
    db.get.return_value = item
    return owner, item, db, tmp_path / "uploads"


def make_image(format="PNG"):
    image = Image.new("RGB", (2, 2), color="red")
    stream = io.BytesIO()
    image.save(stream, format=format)
    return stream.getvalue()


def upload(data, filename="client-name.png", content_type="image/png"):
    class TestUploadFile(UploadFile):
        def __init__(self):
            super().__init__(filename=filename, file=io.BytesIO(data), headers={"content-type": content_type})

        async def read(self, size=-1):
            return self.file.read(size)

        async def close(self):
            self.file.close()

    return TestUploadFile()


def call_upload(item_id, image, owner, db):
    import asyncio
    return asyncio.run(items.upload_lost_item_image(item_id, image, owner, db))


@pytest.mark.parametrize(
    "image_format, extension",
    [("PNG", ".png"), ("JPEG", ".jpg"), ("WEBP", ".webp")],
)
def test_valid_upload_uses_random_filename_and_persists_reference(
    setup_upload, image_format, extension
):
    owner, item, db, root = setup_upload
    image = upload(
        make_image(image_format), filename="../../bad.html", content_type="text/html"
    )

    response = call_upload(item.id, image, owner, db)

    stored = root / Path(response.image_path).name
    assert response.image_path.startswith("uploads/")
    assert Path(response.image_path).name != "../../bad.html"
    assert Path(response.image_path).suffix == extension
    assert stored.is_file()
    assert item.image_path == response.image_path
    db.commit.assert_called_once_with()
    assert list(root.glob(".*.upload")) == []


@pytest.mark.parametrize(
    "data, expected_status",
    [
        (b"", status.HTTP_400_BAD_REQUEST),
        (b"this is not an image", status.HTTP_400_BAD_REQUEST),
        (b"<html>not an image</html>", status.HTTP_400_BAD_REQUEST),
    ],
)
def test_empty_and_malformed_uploads_are_rejected(setup_upload, data, expected_status):
    owner, item, db, root = setup_upload
    with pytest.raises(HTTPException) as error:
        call_upload(item.id, upload(data), owner, db)
    assert error.value.status_code == expected_status
    assert list(root.glob("*")) == []
    db.commit.assert_not_called()


def test_unsupported_actual_image_format_is_rejected(setup_upload):
    owner, item, db, root = setup_upload
    with pytest.raises(HTTPException) as error:
        call_upload(item.id, upload(make_image("GIF"), content_type="image/png"), owner, db)
    assert error.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert list(root.glob("*")) == []
    db.commit.assert_not_called()


def test_oversized_upload_is_rejected_and_temporary_file_removed(setup_upload, monkeypatch):
    owner, item, db, root = setup_upload
    monkeypatch.setattr(items, "settings", Settings(UPLOAD_DIR=str(root), UPLOAD_MAX_SIZE_MB=1))
    data = make_image() + b"x" * (1024 * 1024)

    with pytest.raises(HTTPException) as error:
        call_upload(item.id, upload(data), owner, db)

    assert error.value.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert list(root.glob("*")) == []
    db.commit.assert_not_called()


def test_missing_item_returns_404_before_writing(setup_upload):
    owner, _, db, root = setup_upload
    db.get.return_value = None
    with pytest.raises(HTTPException) as error:
        call_upload(404, upload(make_image()), owner, db)
    assert error.value.status_code == status.HTTP_404_NOT_FOUND
    assert not root.exists()


def test_other_user_cannot_upload(setup_upload):
    _, item, db, root = setup_upload
    with pytest.raises(HTTPException) as error:
        call_upload(item.id, upload(make_image()), SimpleNamespace(id=99), db)
    assert error.value.status_code == status.HTTP_403_FORBIDDEN
    assert not root.exists()
    db.commit.assert_not_called()


def test_database_failure_rolls_back_and_removes_new_file(setup_upload):
    owner, item, db, root = setup_upload
    db.commit.side_effect = SQLAlchemyError("secret database details")

    with pytest.raises(HTTPException) as error:
        call_upload(item.id, upload(make_image()), owner, db)

    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "secret" not in error.value.detail
    db.rollback.assert_called_once_with()
    assert list(root.glob("*")) == []


def test_database_failure_keeps_existing_image(setup_upload):
    owner, item, db, root = setup_upload
    root.mkdir()
    previous_file = root / ("c" * 32 + ".jpg")
    previous_file.write_bytes(b"previous image")
    item.image_path = f"uploads/{previous_file.name}"
    db.commit.side_effect = SQLAlchemyError("database failure")

    with pytest.raises(HTTPException):
        call_upload(item.id, upload(make_image()), owner, db)

    assert previous_file.read_bytes() == b"previous image"


def test_replacement_removes_old_owned_image_only_after_commit(setup_upload):
    owner, item, db, root = setup_upload
    root.mkdir()
    old_path = root / ("d" * 32 + ".jpg")
    old_path.write_bytes(b"old file")
    item.image_path = f"uploads/{old_path.name}"

    response = call_upload(item.id, upload(make_image()), owner, db)

    assert not old_path.exists()
    assert (root / Path(response.image_path).name).is_file()
    db.commit.assert_called_once_with()


def test_upload_route_requires_auth_and_multipart_file_field():
    route = next(
        route
        for route in items.router.routes
        if route.path == "/{item_id}/image" and "POST" in route.methods
    )
    openapi = app.openapi()["paths"]["/api/items/{item_id}/image"]["post"]
    assert "POST" in route.methods
    assert any(dependency.call is dependencies.get_current_user for dependency in route.dependant.dependencies)
    assert openapi["requestBody"]["content"]["multipart/form-data"]
    assert route.response_model.__name__ == "LostItemImageUploadResponse"


def test_missing_authentication_is_rejected(monkeypatch):
    monkeypatch.setattr(
        dependencies,
        "settings",
        Settings(JWT_SECRET_KEY="test-signing-secret-that-is-long-enough"),
    )
    with pytest.raises(HTTPException) as error:
        dependencies.get_current_user(None, Mock())
    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
