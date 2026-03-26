from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.apps.auth.dependencies import get_current_active_user
from app.apps.auth.service import AuthService, InactiveUserError
from app.apps.notifications.dependencies import get_notifications_service
from app.apps.notifications.realtime import notifications_connection_manager
from app.apps.notifications.schemas import (
    NotificationMarkAllReadResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.apps.notifications.service import (
    NotificationsConflictError,
    NotificationsNotFoundError,
    NotificationsService,
    NotificationsValidationError,
)
from app.apps.users.models import User
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import TokenValidationError

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def raise_notifications_http_error(exc: Exception) -> None:
    """Map notification service errors to HTTP exceptions."""

    if isinstance(exc, NotificationsNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if isinstance(exc, NotificationsValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if isinstance(exc, NotificationsConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    raise exc


@router.get(
    "",
    response_model=list[NotificationResponse],
    status_code=status.HTTP_200_OK,
    summary="List internal notifications for the authenticated user",
    description="Return only notifications belonging to the current authenticated user.",
)
def list_my_notifications(
    unread_only: bool = Query(default=False),
    limit: int | None = Query(default=None, ge=1, le=200),
    service: NotificationsService = Depends(get_notifications_service),
    current_user: User = Depends(get_current_active_user),
) -> list[NotificationResponse]:
    notifications = service.list_user_notifications(
        current_user,
        unread_only=unread_only,
        limit=limit,
    )
    return [service.build_notification_response(item) for item in notifications]


@router.get(
    "/unread-count",
    response_model=NotificationUnreadCountResponse,
    status_code=status.HTTP_200_OK,
    summary="Get unread notification count for the authenticated user",
    description="Return the unread internal notification count scoped to the current user.",
)
def get_unread_notification_count(
    service: NotificationsService = Depends(get_notifications_service),
    current_user: User = Depends(get_current_active_user),
) -> NotificationUnreadCountResponse:
    return NotificationUnreadCountResponse(
        unread_count=service.get_unread_count(current_user)
    )


@router.post(
    "/mark-all-read",
    response_model=NotificationMarkAllReadResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark all authenticated user's notifications as read",
)
def mark_all_notifications_as_read(
    service: NotificationsService = Depends(get_notifications_service),
    current_user: User = Depends(get_current_active_user),
) -> NotificationMarkAllReadResponse:
    try:
        updated_count = service.mark_all_as_read(current_user)
    except NotificationsConflictError as exc:
        raise_notifications_http_error(exc)

    return NotificationMarkAllReadResponse(updated_count=updated_count)


@router.post(
    "/{notification_id}/mark-as-read",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark one notification as read for the authenticated user",
)
def mark_notification_as_read(
    notification_id: int,
    service: NotificationsService = Depends(get_notifications_service),
    current_user: User = Depends(get_current_active_user),
) -> NotificationResponse:
    try:
        notification = service.mark_as_read(notification_id, current_user)
    except (
        NotificationsConflictError,
        NotificationsNotFoundError,
    ) as exc:
        raise_notifications_http_error(exc)

    return service.build_notification_response(notification)


@router.websocket("/ws")
async def notifications_websocket(websocket: WebSocket) -> None:
    current_user = await authenticate_notifications_websocket(websocket)
    if current_user is None:
        return

    await notifications_connection_manager.connect(current_user.id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        notifications_connection_manager.disconnect(current_user.id, websocket)


async def authenticate_notifications_websocket(websocket: WebSocket) -> User | None:
    """Authenticate the websocket user from a bearer token or query token."""

    token = extract_websocket_token(websocket)
    if token is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    db = SessionLocal()
    try:
        auth_service = AuthService(db=db, settings=settings)
        user = auth_service.get_authenticated_user_from_token(token)
        return auth_service.ensure_active_user(user)
    except (InactiveUserError, TokenValidationError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    finally:
        db.close()


def extract_websocket_token(websocket: WebSocket) -> str | None:
    """Extract a websocket auth token from query params or Authorization header."""

    token = websocket.query_params.get("token")
    if token is not None:
        normalized_token = token.strip()
        if normalized_token:
            return normalized_token

    authorization_header = websocket.headers.get("authorization")
    if authorization_header is None:
        return None

    scheme, _, credentials = authorization_header.partition(" ")
    if scheme.lower() != "bearer":
        return None

    normalized_credentials = credentials.strip()
    return normalized_credentials or None
