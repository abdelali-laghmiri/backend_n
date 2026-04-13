from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.apps.messages.dependencies import get_messages_service
from app.apps.messages.schemas import (
    MessageCreateRequest,
    MessageListItemResponse,
    MessageResponse,
    MessageTemplateCreateRequest,
    MessageTemplateResponse,
    MessageTemplateUpdateRequest,
    MessageUnreadCountResponse,
)
from app.apps.messages.service import (
    MessagesAuthorizationError,
    MessagesConflictError,
    MessagesNotFoundError,
    MessagesService,
    MessagesValidationError,
)
from app.apps.permissions.dependencies import require_permission
from app.apps.users.models import User

router = APIRouter(prefix="/messages", tags=["Messages"])


def raise_messages_http_error(exc: Exception) -> None:
    if isinstance(exc, MessagesNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if isinstance(exc, MessagesAuthorizationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if isinstance(exc, MessagesValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if isinstance(exc, MessagesConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    raise exc


@router.post(
    "",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a new internal message",
)
def send_message(
    payload: MessageCreateRequest,
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.send")),
) -> MessageResponse:
    try:
        message = service.send_message(current_user, payload)
        return service.get_message(message.id, current_user, mark_read=False)
    except (
        MessagesAuthorizationError,
        MessagesConflictError,
        MessagesNotFoundError,
        MessagesValidationError,
    ) as exc:
        raise_messages_http_error(exc)


@router.post(
    "/{message_id}/reply",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reply within an existing message thread",
)
def reply_to_message(
    message_id: int,
    payload: MessageCreateRequest,
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.send")),
) -> MessageResponse:
    try:
        payload_with_parent = MessageCreateRequest(
            subject=payload.subject,
            body=payload.body,
            recipients=payload.recipients,
            parent_message_id=message_id,
        )
        message = service.send_message(current_user, payload_with_parent)
        return service.get_message(message.id, current_user, mark_read=False)
    except (
        MessagesAuthorizationError,
        MessagesConflictError,
        MessagesNotFoundError,
        MessagesValidationError,
    ) as exc:
        raise_messages_http_error(exc)


@router.get(
    "/inbox",
    response_model=list[MessageListItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List inbox messages for the current user",
)
def list_inbox_messages(
    unread_only: bool = Query(default=False),
    limit: int | None = Query(default=50, ge=1, le=200),
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.read")),
) -> list[MessageListItemResponse]:
    try:
        return service.list_inbox(
            current_user,
            unread_only=unread_only,
            limit=limit,
        )
    except (
        MessagesAuthorizationError,
        MessagesValidationError,
    ) as exc:
        raise_messages_http_error(exc)


@router.get(
    "/sent",
    response_model=list[MessageListItemResponse],
    status_code=status.HTTP_200_OK,
    summary="List messages sent by the current user",
)
def list_sent_messages(
    limit: int | None = Query(default=50, ge=1, le=200),
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.read")),
) -> list[MessageListItemResponse]:
    try:
        return service.list_sent(current_user, limit=limit)
    except MessagesValidationError as exc:
        raise_messages_http_error(exc)


@router.get(
    "/unread-count",
    response_model=MessageUnreadCountResponse,
    status_code=status.HTTP_200_OK,
    summary="Get unread message count",
)
def get_unread_message_count(
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.read")),
) -> MessageUnreadCountResponse:
    return service.get_unread_count(current_user)


@router.get(
    "/{message_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a message by id",
)
def get_message(
    message_id: int,
    mark_as_read: bool = Query(default=True),
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.read")),
) -> MessageResponse:
    try:
        return service.get_message(
            message_id,
            current_user,
            mark_read=mark_as_read,
        )
    except (
        MessagesAuthorizationError,
        MessagesNotFoundError,
    ) as exc:
        raise_messages_http_error(exc)


@router.post(
    "/{message_id}/mark-read",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark one message as read",
)
def mark_message_as_read(
    message_id: int,
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.read")),
) -> MessageResponse:
    try:
        message = service.mark_as_read(message_id, current_user)
        return service.get_message(message.id, current_user, mark_read=False)
    except (
        MessagesAuthorizationError,
        MessagesNotFoundError,
    ) as exc:
        raise_messages_http_error(exc)


# Templates --------------------------------------------------------------


@router.post(
    "/templates",
    response_model=MessageTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a personal message template",
)
def create_message_template(
    payload: MessageTemplateCreateRequest,
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.templates")),
) -> MessageTemplateResponse:
    try:
        template = service.create_template(current_user, payload)
        return MessageTemplateResponse.model_validate(template)
    except (MessagesConflictError, MessagesValidationError) as exc:
        raise_messages_http_error(exc)


@router.get(
    "/templates",
    response_model=list[MessageTemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="List personal message templates",
)
def list_message_templates(
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.templates")),
) -> list[MessageTemplateResponse]:
    return service.list_templates(current_user)


@router.get(
    "/templates/{template_id}",
    response_model=MessageTemplateResponse,
    status_code=status.HTTP_200_OK,
    summary="Get one message template",
)
def get_message_template(
    template_id: int,
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.templates")),
) -> MessageTemplateResponse:
    try:
        template = service.get_template(template_id, current_user)
        return MessageTemplateResponse.model_validate(template)
    except MessagesNotFoundError as exc:
        raise_messages_http_error(exc)


@router.patch(
    "/templates/{template_id}",
    response_model=MessageTemplateResponse,
    status_code=status.HTTP_200_OK,
    summary="Update one message template",
)
def update_message_template(
    template_id: int,
    payload: MessageTemplateUpdateRequest,
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.templates")),
) -> MessageTemplateResponse:
    try:
        template = service.update_template(template_id, current_user, payload)
        return MessageTemplateResponse.model_validate(template)
    except (MessagesNotFoundError, MessagesConflictError, MessagesValidationError) as exc:
        raise_messages_http_error(exc)


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one message template",
    response_class=Response,
)
def delete_message_template(
    template_id: int,
    service: MessagesService = Depends(get_messages_service),
    current_user: User = Depends(require_permission("messages.templates")),
) -> Response:
    try:
        service.delete_template(template_id, current_user)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (MessagesNotFoundError, MessagesConflictError) as exc:
        raise_messages_http_error(exc)
