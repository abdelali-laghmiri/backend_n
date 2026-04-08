from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.apps.announcements.models import AnnouncementAttachment
from app.core.config import settings
from app.shared.uploads import delete_managed_upload, resolve_managed_upload_path

ANNOUNCEMENT_ATTACHMENT_CATEGORY = "announcements"


def _resolve_announcement_attachment_storage_root() -> Path:
    """Resolve the private storage root used for protected announcement attachments."""

    configured_storage_root = os.getenv(
        "MANAGED_ANNOUNCEMENT_ATTACHMENTS_DIR",
        "",
    ).strip()
    if configured_storage_root:
        return Path(configured_storage_root)

    if os.getenv("VERCEL") == "1":
        return Path("/tmp/protected_uploads")

    return Path(__file__).resolve().parents[2] / "_protected_uploads"


ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT = _resolve_announcement_attachment_storage_root()


def build_announcement_attachment_access_url(
    announcement_id: int,
    attachment_id: int,
) -> str:
    """Build the authenticated API URL used to read one announcement attachment."""

    return (
        f"{settings.api_v1_prefix}/announcements/"
        f"{announcement_id}/attachments/{attachment_id}"
    )


def resolve_announcement_attachment_path(
    attachment: AnnouncementAttachment,
) -> Path | None:
    """Resolve the protected attachment file path, migrating legacy public files when found."""

    protected_path = resolve_managed_upload_path(
        attachment.file_url,
        category=ANNOUNCEMENT_ATTACHMENT_CATEGORY,
        storage_root=ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT,
    )
    if protected_path is not None and protected_path.exists():
        return protected_path

    legacy_path = resolve_managed_upload_path(
        attachment.file_url,
        category=ANNOUNCEMENT_ATTACHMENT_CATEGORY,
    )
    if legacy_path is None or not legacy_path.exists():
        return protected_path

    if protected_path is None:
        return legacy_path

    protected_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy_path), str(protected_path))
    return protected_path


def delete_announcement_attachment_file(file_url: str | None) -> None:
    """Delete an attachment file from protected storage and any legacy public location."""

    delete_managed_upload(
        file_url,
        category=ANNOUNCEMENT_ATTACHMENT_CATEGORY,
        storage_root=ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT,
    )
    delete_managed_upload(
        file_url,
        category=ANNOUNCEMENT_ATTACHMENT_CATEGORY,
    )
