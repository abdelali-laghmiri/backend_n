from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.apps.announcements.dependencies import get_announcements_service
from app.apps.announcements.schemas import (
    AnnouncementCreateRequest,
    AnnouncementDetailResponse,
    AnnouncementListItemResponse,
    AnnouncementMarkSeenResponse,
    AnnouncementUpdateRequest,
)
from app.apps.announcements.service import (
    AnnouncementsConflictError,
    AnnouncementsNotFoundError,
    AnnouncementsService,
    AnnouncementsValidationError,
)
from app.apps.announcements.storage import (
    ANNOUNCEMENT_ATTACHMENT_CATEGORY,
    ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT,
    delete_announcement_attachment_file,
    resolve_announcement_attachment_path,
)
from app.apps.permissions.dependencies import get_permissions_service, require_permission
from app.apps.permissions.service import PermissionsService
from app.apps.users.models import User
from app.shared.uploads import (
    ManagedUploadValidationError,
    StoredUploadFile,
    delete_managed_uploads,
    save_managed_upload,
)

router = APIRouter(prefix="/announcements", tags=["Announcements"])

ANNOUNCEMENT_MANAGE_PERMISSION_CODES = (
    "announcements.create",
    "announcements.update",
    "announcements.delete",
)
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


def raise_announcements_http_error(exc: Exception) -> None:
    """Map announcement service errors to HTTP exceptions."""

    if isinstance(exc, AnnouncementsNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if isinstance(exc, AnnouncementsValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if isinstance(exc, AnnouncementsConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    raise exc


@router.get(
    "",
    response_model=list[AnnouncementListItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List company announcements",
)
def list_announcements(
    include_all: bool = Query(default=False),
    limit: int | None = Query(default=None, ge=1, le=100),
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.read")),
    permissions_service: PermissionsService = Depends(get_permissions_service),
) -> list[AnnouncementListItemResponse]:
    if include_all and not _can_manage_announcements(current_user, permissions_service):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Announcement management permissions are required to include hidden records.",
        )

    announcements = service.list_announcements(
        current_user,
        include_all=include_all,
        limit=limit,
    )
    return service.build_announcement_list_responses(announcements, current_user)


@router.get(
    "/{announcement_id}",
    response_model=AnnouncementDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get one announcement by id",
)
def get_announcement(
    announcement_id: int,
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.read")),
    permissions_service: PermissionsService = Depends(get_permissions_service),
) -> AnnouncementDetailResponse:
    try:
        announcement = service.get_announcement_for_user(
            announcement_id,
            current_user,
            include_all=_can_manage_announcements(current_user, permissions_service),
        )
    except AnnouncementsNotFoundError as exc:
        raise_announcements_http_error(exc)

    return service.build_announcement_detail_response(announcement, current_user)


@router.post(
    "",
    response_model=AnnouncementDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an announcement",
)
def create_announcement(
    payload: AnnouncementCreateRequest,
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.create")),
) -> AnnouncementDetailResponse:
    try:
        announcement = service.create_announcement(payload, current_user)
    except (AnnouncementsConflictError, AnnouncementsValidationError) as exc:
        raise_announcements_http_error(exc)

    return service.build_announcement_detail_response(announcement, current_user)


@router.put(
    "/{announcement_id}",
    response_model=AnnouncementDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an announcement",
)
def update_announcement(
    announcement_id: int,
    payload: AnnouncementUpdateRequest,
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.update")),
) -> AnnouncementDetailResponse:
    try:
        announcement = service.update_announcement(
            announcement_id,
            payload,
            current_user,
        )
    except (
        AnnouncementsConflictError,
        AnnouncementsNotFoundError,
        AnnouncementsValidationError,
    ) as exc:
        raise_announcements_http_error(exc)

    return service.build_announcement_detail_response(announcement, current_user)


@router.delete(
    "/{announcement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Delete an announcement by deactivating it",
)
def delete_announcement(
    announcement_id: int,
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.delete")),
):
    try:
        service.deactivate_announcement(announcement_id, current_user)
    except (AnnouncementsConflictError, AnnouncementsNotFoundError) as exc:
        raise_announcements_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{announcement_id}/attachments",
    response_model=AnnouncementDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload attachments for an announcement",
)
async def add_announcement_attachments(
    announcement_id: int,
    files: list[UploadFile] = File(...),
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.update")),
) -> AnnouncementDetailResponse:
    stored_uploads = await _store_announcement_uploads(files)
    try:
        announcement = service.add_attachments(
            announcement_id,
            current_user,
            stored_uploads,
        )
    except (
        AnnouncementsConflictError,
        AnnouncementsNotFoundError,
        AnnouncementsValidationError,
    ) as exc:
        delete_managed_uploads(
            [upload.file_url for upload in stored_uploads],
            category=ANNOUNCEMENT_ATTACHMENT_CATEGORY,
            storage_root=ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT,
        )
        raise_announcements_http_error(exc)

    return service.build_announcement_detail_response(announcement, current_user)


@router.get(
    "/{announcement_id}/attachments/{attachment_id}",
    response_class=FileResponse,
    summary="Open one announcement attachment",
)
def get_announcement_attachment(
    announcement_id: int,
    attachment_id: int,
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.read")),
    permissions_service: PermissionsService = Depends(get_permissions_service),
) -> FileResponse:
    try:
        attachment = service.get_attachment_for_user(
            announcement_id,
            attachment_id,
            current_user,
            include_all=_can_manage_announcements(current_user, permissions_service),
        )
        attachment_path = resolve_announcement_attachment_path(attachment)
        if attachment_path is None or not attachment_path.exists():
            raise AnnouncementsNotFoundError("Announcement attachment not found.")
    except AnnouncementsNotFoundError as exc:
        raise_announcements_http_error(exc)

    return FileResponse(
        attachment_path,
        media_type=attachment.content_type,
        filename=attachment.original_file_name,
        content_disposition_type="inline",
    )


@router.delete(
    "/{announcement_id}/attachments/{attachment_id}",
    response_model=AnnouncementDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete one announcement attachment",
)
def delete_announcement_attachment(
    announcement_id: int,
    attachment_id: int,
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.update")),
) -> AnnouncementDetailResponse:
    try:
        file_url = service.remove_attachment(
            announcement_id,
            attachment_id,
            current_user,
        )
        announcement = service.get_announcement_for_user(
            announcement_id,
            current_user,
            include_all=True,
        )
    except (
        AnnouncementsConflictError,
        AnnouncementsNotFoundError,
    ) as exc:
        raise_announcements_http_error(exc)

    delete_announcement_attachment_file(file_url)
    return service.build_announcement_detail_response(announcement, current_user)


@router.post(
    "/{announcement_id}/mark-seen",
    response_model=AnnouncementMarkSeenResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark an announcement as seen by the current user",
)
def mark_announcement_as_seen(
    announcement_id: int,
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.read")),
) -> AnnouncementMarkSeenResponse:
    try:
        read_record = service.mark_seen(announcement_id, current_user)
    except (
        AnnouncementsConflictError,
        AnnouncementsNotFoundError,
        AnnouncementsValidationError,
    ) as exc:
        raise_announcements_http_error(exc)

    return service.build_mark_seen_response(read_record)


def _can_manage_announcements(
    current_user: User,
    permissions_service: PermissionsService,
) -> bool:
    """Return whether the current user can access announcement management views."""

    return any(
        permissions_service.user_has_permission(current_user, permission_code)
        for permission_code in ANNOUNCEMENT_MANAGE_PERMISSION_CODES
    )


async def _store_announcement_uploads(
    files: list[UploadFile],
) -> list[StoredUploadFile]:
    """Store announcement uploads locally and clean up partial writes on validation errors."""

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one attachment file is required.",
        )

    stored_uploads: list[StoredUploadFile] = []
    try:
        for upload in files:
            stored_uploads.append(
                await save_managed_upload(
                    upload,
                    category=ANNOUNCEMENT_ATTACHMENT_CATEGORY,
                    allowed_content_types=ANNOUNCEMENT_ATTACHMENT_ALLOWED_CONTENT_TYPES,
                    allowed_suffixes=ANNOUNCEMENT_ATTACHMENT_ALLOWED_SUFFIXES,
                    max_bytes=ANNOUNCEMENT_ATTACHMENT_MAX_BYTES,
                    storage_root=ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT,
                )
            )
    except ManagedUploadValidationError as exc:
        delete_managed_uploads(
            [upload.file_url for upload in stored_uploads],
            category=ANNOUNCEMENT_ATTACHMENT_CATEGORY,
            storage_root=ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception:
        delete_managed_uploads(
            [upload.file_url for upload in stored_uploads],
            category=ANNOUNCEMENT_ATTACHMENT_CATEGORY,
            storage_root=ANNOUNCEMENT_ATTACHMENT_STORAGE_ROOT,
        )
        raise

    return stored_uploads
