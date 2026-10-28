import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from PIL import Image

from app.api import dependencies, items
from app.core.config import Settings
from app.main import app


@pytest.fixture
def image_fixture(monkeypatch, tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(
        items, "settings", Settings(UPLOAD_DIR=str(root), UPLOAD_MAX_SIZE_MB=5)
    )
    owner = SimpleNamespace(id=5, is_active=True)
    image_bytes = io.BytesIO()
    Image.new("RGB", (3, 2), color="blue").save(image_bytes, format="PNG")
    return root, owner, image_bytes.getvalue()


def test_authenticated_user_can_retrieve_image_with_content_derived_type(image_fixture):
    root, user, image_bytes = image_fixture
    stored_file = root / ("a" * 32 + ".jpg")
    stored_file.write_bytes(image_bytes)
    item = SimpleNamespace(id=42, image_path=f"uploads/{stored_file.name}")
    db = Mock()
    db.get.return_value = item

    response = items.get_lost_item_image(item.id, user, db)

    assert isinstance(response, FileResponse)
    assert response.path == stored_file
    assert response.media_type == "image/png"  # Format comes from bytes, not suffix.
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == 'inline; filename="lost-item-42.png"'
    assert stored_file.read_bytes() == image_bytes
    assert str(root) not in str(response.headers)


def test_missing_item_returns_404(image_fixture):
    _, user, _ = image_fixture
    db = Mock()
    db.get.return_value = None
    with pytest.raises(HTTPException) as error:
        items.get_lost_item_image(99, user, db)
    assert error.value.status_code == status.HTTP_404_NOT_FOUND
    assert error.value.detail == "Image not found"


def test_item_without_image_returns_404(image_fixture):
    _, user, _ = image_fixture
    db = Mock()
    db.get.return_value = SimpleNamespace(id=42, image_path=None)
    with pytest.raises(HTTPException) as error:
        items.get_lost_item_image(42, user, db)
    assert error.value.status_code == status.HTTP_404_NOT_FOUND
    assert error.value.detail == "Image not found"


def test_missing_image_file_returns_404(image_fixture):
    _, user, _ = image_fixture
    db = Mock()
    db.get.return_value = SimpleNamespace(id=42, image_path="uploads/missing.png")
    with pytest.raises(HTTPException) as error:
        items.get_lost_item_image(42, user, db)
    assert error.value.status_code == status.HTTP_404_NOT_FOUND
    assert error.value.detail == "Image not found"


@pytest.mark.parametrize(
    "reference",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "uploads/../../etc/passwd",
        "outside/anything.png",
        r"uploads\..\outside.png",
    ],
)
def test_invalid_stored_paths_return_404(image_fixture, reference):
    _, user, _ = image_fixture
    db = Mock()
    db.get.return_value = SimpleNamespace(id=42, image_path=reference)
    with pytest.raises(HTTPException) as error:
        items.get_lost_item_image(42, user, db)
    assert error.value.status_code == status.HTTP_404_NOT_FOUND
    assert error.value.detail == "Image not found"


def test_symlink_escaping_storage_root_is_rejected(image_fixture, tmp_path):
    root, user, _ = image_fixture
    outside_file = tmp_path / "outside.png"
    outside_file.write_bytes(b"not an image")
    linked_file = root / ("b" * 32 + ".png")
    linked_file.symlink_to(outside_file)
    db = Mock()
    db.get.return_value = SimpleNamespace(id=42, image_path=f"uploads/{linked_file.name}")
    with pytest.raises(HTTPException) as error:
        items.get_lost_item_image(42, user, db)
    assert error.value.status_code == status.HTTP_404_NOT_FOUND


def test_retrieval_route_requires_existing_authentication_dependency():
    route = next(
        route
        for route in items.router.routes
        if route.path == "/{item_id}/image" and "GET" in route.methods
    )
    openapi = app.openapi()["paths"]["/api/items/{item_id}/image"]["get"]
    assert any(
        dependency.call is dependencies.get_current_user
        for dependency in route.dependant.dependencies
    )
    assert "security" in openapi
    assert set(openapi["responses"]["200"]["content"]) == {
        "image/jpeg",
        "image/png",
        "image/webp",
    }
    assert route.response_class is FileResponse
