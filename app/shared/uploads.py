from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from starlette.datastructures import UploadFile

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
UPLOADS_DIR = STATIC_DIR / "uploads"


class ManagedUploadValidationError(ValueError):
    """Raised when an uploaded file does not meet the managed-upload rules."""


@dataclass(slots=True)
class StoredUploadFile:
    """Metadata returned after storing one managed upload on local disk."""

    original_file_name: str
    stored_file_name: str
    file_url: str
    content_type: str
    file_extension: str
    file_size_bytes: int


async def save_managed_upload(
    upload: UploadFile,
    *,
    category: str,
    allowed_content_types: dict[str, str],
    allowed_suffixes: set[str],
    max_bytes: int,
) -> StoredUploadFile:
    """Persist one uploaded file inside the managed static uploads directory."""

    if not upload.filename:
        await upload.close()
        raise ManagedUploadValidationError("Uploaded file name is required.")

    content_type = (upload.content_type or "").lower()
    original_suffix = Path(upload.filename).suffix.lower()
    is_allowed_content_type = content_type in allowed_content_types
    is_allowed_suffix = original_suffix in allowed_suffixes

    if not is_allowed_content_type and not is_allowed_suffix:
        await upload.close()
        raise ManagedUploadValidationError("Uploaded file type is not supported.")

    file_bytes = await upload.read(max_bytes + 1)
    await upload.close()

    if not file_bytes:
        raise ManagedUploadValidationError("Uploaded file cannot be empty.")

    if len(file_bytes) > max_bytes:
        raise ManagedUploadValidationError(
            f"Uploaded file must be {max_bytes // (1024 * 1024)} MB or smaller."
        )

    file_extension = (
        original_suffix
        if is_allowed_suffix and original_suffix
        else allowed_content_types.get(content_type, original_suffix)
    )
    if not file_extension:
        file_extension = ".bin"

    content_type = content_type or "application/octet-stream"

    destination_dir = UPLOADS_DIR / category
    destination_dir.mkdir(parents=True, exist_ok=True)
    stored_file_name = f"{uuid4().hex}{file_extension}"
    destination = destination_dir / stored_file_name
    destination.write_bytes(file_bytes)

    return StoredUploadFile(
        original_file_name=Path(upload.filename).name,
        stored_file_name=stored_file_name,
        file_url=f"/static/uploads/{category}/{stored_file_name}",
        content_type=content_type,
        file_extension=file_extension,
        file_size_bytes=len(file_bytes),
    )


def delete_managed_upload(file_url: str | None, *, category: str | None = None) -> None:
    """Delete one locally managed upload when it belongs to the expected directory."""

    target = _resolve_managed_upload_path(file_url, category=category)
    if target is None or not target.exists():
        return

    target.unlink()


def delete_managed_uploads(
    file_urls: list[str],
    *,
    category: str | None = None,
) -> None:
    """Delete multiple locally managed uploads, ignoring missing targets."""

    for file_url in file_urls:
        delete_managed_upload(file_url, category=category)


def _resolve_managed_upload_path(
    file_url: str | None,
    *,
    category: str | None = None,
) -> Path | None:
    """Resolve a managed upload URL to a safe local file path when possible."""

    if file_url is None or not file_url.startswith("/static/uploads/"):
        return None

    relative_path = Path(file_url.removeprefix("/static/"))
    target = (STATIC_DIR / relative_path).resolve()
    uploads_root = UPLOADS_DIR.resolve()

    if not _is_relative_to(target, uploads_root):
        return None

    if category is not None:
        expected_root = (UPLOADS_DIR / category).resolve()
        if not _is_relative_to(target, expected_root):
            return None

    return target


def _is_relative_to(path: Path, root: Path) -> bool:
    """Return whether one path stays inside another path."""

    try:
        path.relative_to(root)
    except ValueError:
        return False

    return True
