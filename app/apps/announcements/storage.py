from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx
from starlette.datastructures import UploadFile

from app.apps.announcements.models import AnnouncementAttachment
from app.core.config import settings
from app.shared.uploads import ManagedUploadValidationError, StoredUploadFile

ANNOUNCEMENT_ATTACHMENT_CATEGORY = "announcements"
ANNOUNCEMENT_ATTACHMENT_ALLOWED_CONTENT_TYPES = {
    "application/msword": ".doc",
    "application/pdf": ".pdf",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "text/csv": ".csv",
    "text/plain": ".txt",
}
ANNOUNCEMENT_ATTACHMENT_ALLOWED_SUFFIXES = {
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".txt",
    ".webp",
    ".xls",
    ".xlsx",
}
ANNOUNCEMENT_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024


class AnnouncementAttachmentStorageError(RuntimeError):
    """Raised when Supabase Storage operations fail."""


def _resolve_supabase_url() -> str:
    value = (settings.supabase_url or "").strip()
    return value.rstrip("/")


def _resolve_supabase_service_role_key() -> str:
    if settings.supabase_service_role_key is None:
        return ""

    return settings.supabase_service_role_key.get_secret_value().strip()


def _resolve_supabase_bucket() -> str:
    return (settings.supabase_storage_bucket_announcements or "announcement-attachments").strip() or "announcement-attachments"


def _require_supabase_storage_config() -> tuple[str, str, str]:
    supabase_url = _resolve_supabase_url()
    service_role_key = _resolve_supabase_service_role_key()
    bucket = _resolve_supabase_bucket()
    if not supabase_url or not service_role_key or not bucket:
        raise AnnouncementAttachmentStorageError(
            "Supabase Storage is not configured. Set SUPABASE_URL, "
            "SUPABASE_SERVICE_ROLE_KEY, and SUPABASE_STORAGE_BUCKET_ANNOUNCEMENTS."
        )

    return supabase_url, service_role_key, bucket


def build_announcement_attachment_access_url(
    announcement_id: int,
    attachment_id: int,
) -> str:
    """Build the authenticated API URL used to read one announcement attachment."""

    return (
        f"{settings.api_v1_prefix}/announcements/"
        f"{announcement_id}/attachments/{attachment_id}"
    )


def _normalize_object_path(file_url: str | None) -> str:
    if file_url is None:
        raise AnnouncementAttachmentStorageError("Announcement attachment path is missing.")

    normalized = file_url.strip()
    if not normalized:
        raise AnnouncementAttachmentStorageError("Announcement attachment path is missing.")

    if normalized.startswith("/static/uploads/"):
        normalized = normalized.removeprefix("/static/uploads/")

    return normalized.lstrip("/")


async def store_announcement_upload(
    upload: UploadFile,
    *,
    allowed_content_types: dict[str, str],
    allowed_suffixes: set[str],
    max_bytes: int,
) -> StoredUploadFile:
    """Validate and upload one attachment file to Supabase Storage."""

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

    normalized_content_type = content_type or "application/octet-stream"
    stored_file_name = f"{uuid4().hex}{file_extension}"
    object_path = f"{ANNOUNCEMENT_ATTACHMENT_CATEGORY}/{stored_file_name}"

    supabase_url, service_role_key, bucket = _require_supabase_storage_config()
    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": normalized_content_type,
        "x-upsert": "false",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                upload_url,
                content=file_bytes,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise AnnouncementAttachmentStorageError(
            "Failed to upload attachment to Supabase Storage."
        ) from exc

    if response.status_code >= 400:
        raise AnnouncementAttachmentStorageError(
            "Failed to upload attachment to Supabase Storage."
        )

    return StoredUploadFile(
        original_file_name=Path(upload.filename).name,
        stored_file_name=stored_file_name,
        file_url=object_path,
        content_type=normalized_content_type,
        file_extension=file_extension,
        file_size_bytes=len(file_bytes),
    )


def build_announcement_attachment_signed_url(
    attachment: AnnouncementAttachment,
    *,
    expires_in_seconds: int = 120,
) -> str:
    """Build a short-lived signed URL for one private Supabase attachment."""

    object_path = _normalize_object_path(attachment.file_url)
    supabase_url, service_role_key, bucket = _require_supabase_storage_config()
    sign_url = f"{supabase_url}/storage/v1/object/sign/{bucket}/{object_path}"
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    payload = {"expiresIn": max(60, min(expires_in_seconds, 3600))}

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(sign_url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise AnnouncementAttachmentStorageError(
            "Failed to create signed URL for announcement attachment."
        ) from exc

    if response.status_code >= 400:
        raise AnnouncementAttachmentStorageError(
            "Failed to create signed URL for announcement attachment."
        )

    data = response.json()
    signed_url = data.get("signedURL") or data.get("signedUrl")
    if not signed_url:
        raise AnnouncementAttachmentStorageError(
            "Supabase Storage did not return a signed URL."
        )

    if signed_url.startswith("http://") or signed_url.startswith("https://"):
        return signed_url

    return f"{supabase_url}{signed_url}"


def delete_announcement_attachment_file(file_url: str | None) -> None:
    """Delete one attachment object from Supabase Storage."""

    object_path = _normalize_object_path(file_url)
    supabase_url, service_role_key, bucket = _require_supabase_storage_config()
    delete_url = f"{supabase_url}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.delete(delete_url, headers=headers)
    except httpx.HTTPError as exc:
        raise AnnouncementAttachmentStorageError(
            "Failed to delete attachment from Supabase Storage."
        ) from exc

    if response.status_code >= 400:
        raise AnnouncementAttachmentStorageError(
            "Failed to delete attachment from Supabase Storage."
        )
