from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.notifications.models import Notification, NotificationTypeEnum, utcnow
from app.apps.notifications.realtime import notifications_connection_manager
from app.apps.notifications.schemas import NotificationResponse
from app.apps.users.models import User


class NotificationsConflictError(RuntimeError):
    """Raised when a notification persistence conflict occurs."""


class NotificationsNotFoundError(RuntimeError):
    """Raised when a user-scoped notification cannot be found."""


class NotificationsValidationError(RuntimeError):
    """Raised when notification input is invalid."""


class NotificationsService:
    """Service layer for internal notifications and realtime delivery."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.connection_manager = notifications_connection_manager

    def create_notification(
        self,
        *,
        recipient_user_id: int,
        title: str,
        message: str,
        notification_type: NotificationTypeEnum | str,
        target_url: str | None = None,
        commit: bool = True,
        publish_realtime: bool = True,
    ) -> Notification:
        """Create one notification, optionally committing and publishing immediately."""

        if publish_realtime and not commit:
            raise NotificationsValidationError(
                "Realtime publish requires a committed notification record."
            )

        notification = Notification(
            recipient_user_id=recipient_user_id,
            title=self._normalize_required_text(title, label="Notification title"),
            message=self._normalize_required_text(message, label="Notification message"),
            type=self._normalize_notification_type(notification_type),
            is_read=False,
            read_at=None,
            target_url=self._normalize_optional_text(target_url),
        )
        self.db.add(notification)

        if commit:
            notification = self._commit_and_refresh(
                notification,
                conflict_message="Failed to create the notification.",
            )

        if publish_realtime:
            self.publish_realtime_notification(notification)

        return notification

    def list_user_notifications(
        self,
        current_user: User,
        *,
        unread_only: bool = False,
        limit: int | None = None,
    ) -> list[Notification]:
        """List notifications belonging only to the authenticated user."""

        statement: Select[tuple[Notification]] = select(Notification).where(
            Notification.recipient_user_id == current_user.id
        )
        if unread_only:
            statement = statement.where(Notification.is_read.is_(False))

        statement = statement.order_by(Notification.created_at.desc(), Notification.id.desc())
        if limit is not None:
            statement = statement.limit(limit)

        return list(self.db.execute(statement).scalars().all())

    def get_unread_count(self, current_user: User) -> int:
        """Return the unread notification count for the authenticated user."""

        statement = select(func.count(Notification.id)).where(
            Notification.recipient_user_id == current_user.id,
            Notification.is_read.is_(False),
        )
        return int(self.db.execute(statement).scalar_one())

    def mark_as_read(self, notification_id: int, current_user: User) -> Notification:
        """Mark one notification as read for the authenticated recipient only."""

        notification = self._get_user_notification(notification_id, current_user)
        if notification.is_read:
            return notification

        notification.is_read = True
        notification.read_at = utcnow()
        self.db.add(notification)
        return self._commit_and_refresh(
            notification,
            conflict_message="Failed to mark the notification as read.",
        )

    def mark_all_as_read(self, current_user: User) -> int:
        """Mark all unread notifications as read for the authenticated user."""

        unread_notifications = list(
            self.db.execute(
                select(Notification).where(
                    Notification.recipient_user_id == current_user.id,
                    Notification.is_read.is_(False),
                )
            )
            .scalars()
            .all()
        )
        if not unread_notifications:
            return 0

        read_at = utcnow()
        for notification in unread_notifications:
            notification.is_read = True
            notification.read_at = read_at
            self.db.add(notification)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise NotificationsConflictError(
                "Failed to mark all notifications as read."
            ) from exc

        return len(unread_notifications)

    def build_notification_response(self, notification: Notification) -> NotificationResponse:
        """Build the API response schema for a notification record."""

        return NotificationResponse.model_validate(notification)

    def publish_realtime_notification(self, notification: Notification) -> None:
        """Push one persisted notification to the recipient if connected."""

        notification_response = self.build_notification_response(notification)
        self.publish_realtime_to_user(
            notification.recipient_user_id,
            notification_response,
        )

    def publish_realtime_to_user(
        self,
        recipient_user_id: int,
        notification: NotificationResponse,
    ) -> None:
        """Push a notification payload to the connected recipient, if any."""

        self.connection_manager.publish_to_user_threadsafe(
            recipient_user_id,
            {
                "event": "notification_created",
                "notification": notification.model_dump(mode="json"),
            },
        )

    def _get_user_notification(self, notification_id: int, current_user: User) -> Notification:
        """Return one notification only if it belongs to the authenticated user."""

        statement = (
            select(Notification)
            .where(
                Notification.id == notification_id,
                Notification.recipient_user_id == current_user.id,
            )
            .limit(1)
        )
        notification = self.db.execute(statement).scalar_one_or_none()
        if notification is None:
            raise NotificationsNotFoundError("Notification not found.")

        return notification

    def _normalize_required_text(self, value: str, *, label: str) -> str:
        """Normalize a required notification text field."""

        normalized_value = value.strip()
        if not normalized_value:
            raise NotificationsValidationError(f"{label} cannot be blank.")

        return normalized_value

    def _normalize_optional_text(self, value: str | None) -> str | None:
        """Normalize an optional notification text field."""

        if value is None:
            return None

        normalized_value = value.strip()
        return normalized_value or None

    def _normalize_notification_type(
        self,
        value: NotificationTypeEnum | str,
    ) -> str:
        """Normalize a notification type value for persistence."""

        if isinstance(value, NotificationTypeEnum):
            return value.value

        normalized_value = value.strip()
        if not normalized_value:
            raise NotificationsValidationError("Notification type cannot be blank.")

        return normalized_value

    def _commit_and_refresh(
        self,
        notification: Notification,
        *,
        conflict_message: str,
    ) -> Notification:
        """Commit the transaction and refresh the target notification."""

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise NotificationsConflictError(conflict_message) from exc

        self.db.refresh(notification)
        return notification
