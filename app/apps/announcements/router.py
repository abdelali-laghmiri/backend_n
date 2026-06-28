from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

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
    ANNOUNCEMENT_ATTACHMENT_MAX_BYTES,
    ANNOUNCEMENT_ATTACHMENT_ALLOWED_CONTENT_TYPES,
    ANNOUNCEMENT_ATTACHMENT_ALLOWED_SUFFIXES,
    AnnouncementAttachmentStorageError,
    build_announcement_attachment_signed_url,
    delete_announcement_attachment_file,
    store_announcement_upload,
)
from app.apps.permissions.dependencies import get_permissions_service, require_permission
from app.apps.permissions.service import PermissionsService
from app.apps.users.models import User
from app.shared.uploads import (
    ManagedUploadValidationError,
    StoredUploadFile,
)

router = APIRouter(prefix="/announcements", tags=["Announcements"])

ANNOUNCEMENT_MANAGE_PERMISSION_CODES = (
    "announcements.create",
    "announcements.update",
    "announcements.delete",
)
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
    limit: int = Query(default=100, ge=1, le=1000, description="Max records per page"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
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
        offset=offset,
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
    summary="Create an announcement with optional attachments",
)
async def create_announcement(
    title: str = Form(...),
    summary: str = Form(...),
    content: str = Form(...),
    type: str = Form(...),
    is_pinned: bool = Form(default=False),
    is_active: bool = Form(default=True),
    published_at: datetime = Form(...),
    expires_at: datetime | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.create")),
) -> AnnouncementDetailResponse:
    try:
        payload = AnnouncementCreateRequest(
            title=title,
            summary=summary,
            content=content,
            type=type,
            is_pinned=is_pinned,
            is_active=is_active,
            published_at=published_at,
            expires_at=expires_at,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    stored_uploads: list[StoredUploadFile] = []
    if files:
        stored_uploads = await _store_announcement_uploads(files)

    try:
        announcement = service.create_announcement(payload, current_user)
        if stored_uploads:
            announcement = service.add_attachments(
                announcement.id,
                current_user,
                stored_uploads,
            )
    except (AnnouncementsConflictError, AnnouncementsValidationError) as exc:
        if stored_uploads:
            _cleanup_uploaded_announcement_files(stored_uploads)
        raise_announcements_http_error(exc)
    except AnnouncementsNotFoundError as exc:
        if stored_uploads:
            _cleanup_uploaded_announcement_files(stored_uploads)
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
        _cleanup_uploaded_announcement_files(stored_uploads)
        raise_announcements_http_error(exc)

    return service.build_announcement_detail_response(announcement, current_user)


@router.get("/{announcement_id}/attachments/{attachment_id}", summary="Open one announcement attachment")
def get_announcement_attachment(
    announcement_id: int,
    attachment_id: int,
    service: AnnouncementsService = Depends(get_announcements_service),
    current_user: User = Depends(require_permission("announcements.read")),
    permissions_service: PermissionsService = Depends(get_permissions_service),
) -> RedirectResponse:
    try:
        attachment = service.get_attachment_for_user(
            announcement_id,
            attachment_id,
            current_user,
            include_all=_can_manage_announcements(current_user, permissions_service),
        )
        signed_url = build_announcement_attachment_signed_url(attachment)
    except AnnouncementsNotFoundError as exc:
        raise_announcements_http_error(exc)
    except AnnouncementAttachmentStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return RedirectResponse(url=signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


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
    try:
        delete_announcement_attachment_file(file_url)
    except AnnouncementAttachmentStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

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


def _cleanup_uploaded_announcement_files(stored_uploads: list[StoredUploadFile]) -> None:
    for stored_upload in stored_uploads:
        try:
            delete_announcement_attachment_file(stored_upload.file_url)
        except AnnouncementAttachmentStorageError:
            continue


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
                await store_announcement_upload(
                    upload,
                    allowed_content_types=ANNOUNCEMENT_ATTACHMENT_ALLOWED_CONTENT_TYPES,
                    allowed_suffixes=ANNOUNCEMENT_ATTACHMENT_ALLOWED_SUFFIXES,
                    max_bytes=ANNOUNCEMENT_ATTACHMENT_MAX_BYTES,
                )
            )
    except ManagedUploadValidationError as exc:
        _cleanup_uploaded_announcement_files(stored_uploads)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except AnnouncementAttachmentStorageError as exc:
        _cleanup_uploaded_announcement_files(stored_uploads)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception:
        _cleanup_uploaded_announcement_files(stored_uploads)
        raise

    return stored_uploads
