from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from uuid import uuid4

from starlette.datastructures import UploadFile

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
UPLOADS_URL_PREFIX = "/static/uploads"


def _resolve_uploads_dir() -> Path:
    """Resolve the uploads directory, using a writable path on serverless runtimes."""

    configured_uploads_dir = os.getenv("MANAGED_UPLOADS_DIR", "").strip()
    if configured_uploads_dir:
        return Path(configured_uploads_dir)

    # Vercel serverless deployments expose a read-only application directory.
    if os.getenv("VERCEL") == "1":
        return Path("/tmp/uploads")

    return STATIC_DIR / "uploads"


UPLOADS_DIR = _resolve_uploads_dir()


class ManagedUploadValidationError(ValueError):
    """Raised when an uploaded file does not meet the managed-upload rules."""


def ensure_uploads_dir_exists() -> Path:
    """Create the managed uploads root before StaticFiles validates it."""

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOADS_DIR


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
    storage_root: Path | None = None,
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

    destination_root = storage_root or UPLOADS_DIR
    destination_dir = destination_root / category
    destination_dir.mkdir(parents=True, exist_ok=True)
    stored_file_name = f"{uuid4().hex}{file_extension}"
    destination = destination_dir / stored_file_name
    destination.write_bytes(file_bytes)

    return StoredUploadFile(
        original_file_name=Path(upload.filename).name,
        stored_file_name=stored_file_name,
        file_url=f"{UPLOADS_URL_PREFIX}/{category}/{stored_file_name}",
        content_type=content_type,
        file_extension=file_extension,
        file_size_bytes=len(file_bytes),
    )


def delete_managed_upload(
    file_url: str | None,
    *,
    category: str | None = None,
    storage_root: Path | None = None,
) -> None:
    """Delete one locally managed upload when it belongs to the expected directory."""

    target = resolve_managed_upload_path(
        file_url,
        category=category,
        storage_root=storage_root,
    )
    if target is None or not target.exists():
        return

    target.unlink()


def delete_managed_uploads(
    file_urls: list[str],
    *,
    category: str | None = None,
    storage_root: Path | None = None,
) -> None:
    """Delete multiple locally managed uploads, ignoring missing targets."""

    for file_url in file_urls:
        delete_managed_upload(
            file_url,
            category=category,
            storage_root=storage_root,
        )


def resolve_managed_upload_path(
    file_url: str | None,
    *,
    category: str | None = None,
    storage_root: Path | None = None,
) -> Path | None:
    """Resolve a managed upload URL to a safe local file path when possible."""

    if file_url is None or not file_url.startswith(f"{UPLOADS_URL_PREFIX}/"):
        return None

    relative_path = Path(file_url.removeprefix(f"{UPLOADS_URL_PREFIX}/"))
    uploads_base = storage_root or UPLOADS_DIR
    target = (uploads_base / relative_path).resolve()
    uploads_root = uploads_base.resolve()

    if not _is_relative_to(target, uploads_root):
        return None

    if category is not None:
        expected_root = (uploads_base / category).resolve()
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
