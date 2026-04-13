from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.messages.models import (
    Message,
    MessagePermissionEnum,
    MessageRecipient,
    MessageTemplate,
    utcnow,
)
from app.apps.messages.schemas import (
    MessageCreateRequest,
    MessageListItemResponse,
    MessageRecipientResponse,
    MessageRecipientInput,
    MessageResponse,
    MessageTemplateCreateRequest,
    MessageTemplateResponse,
    MessageTemplateUpdateRequest,
    MessageUnreadCountResponse,
    UserSummary,
)
from app.apps.notifications.models import NotificationTypeEnum
from app.apps.notifications.service import NotificationsService
from app.apps.users.models import User


class MessagesValidationError(RuntimeError):
    """Raised when a message payload is invalid."""


class MessagesNotFoundError(RuntimeError):
    """Raised when a message or template cannot be found."""


class MessagesAuthorizationError(RuntimeError):
    """Raised when a user is not allowed to access a message."""


class MessagesConflictError(RuntimeError):
    """Raised when a persistence conflict occurs."""


@dataclass
class _NormalizedRecipient:
    user_id: int
    permission: MessagePermissionEnum


class MessagesService:
    """Service layer for internal mail messages and templates."""

    def __init__(self, db: Session, notifications_service: NotificationsService) -> None:
        self.db = db
        self.notifications_service = notifications_service

    # Message composition -------------------------------------------------
    def send_message(self, sender: User, payload: MessageCreateRequest) -> Message:
        """Compose a new message or reply and deliver to recipients."""

        recipients = self._normalize_recipients(payload.recipients)

        parent_message = None
        conversation_id = None
        if payload.parent_message_id is not None:
            parent_message = self._get_message_for_user(
                payload.parent_message_id,
                sender,
                mark_read=False,
            )
            if not self._user_can_reply(parent_message, sender):
                raise MessagesAuthorizationError("You cannot reply to this message.")

            conversation_id = parent_message.conversation_id or parent_message.id

        message = Message(
            subject=payload.subject,
            body=payload.body,
            sender_user_id=sender.id,
            conversation_id=conversation_id,
            parent_message_id=parent_message.id if parent_message else None,
        )
        self.db.add(message)
        self.db.flush()

        if message.conversation_id is None:
            message.conversation_id = message.id
            self.db.add(message)

        for recipient in recipients:
            record = MessageRecipient(
                message_id=message.id,
                recipient_user_id=recipient.user_id,
                permission=recipient.permission.value,
                is_read=False,
                read_at=None,
            )
            self.db.add(record)

        message = self._commit_and_refresh(
            message,
            conflict_message="Failed to send the message.",
        )

        self._send_notifications(message, recipients)
        return message

    # Message reads -------------------------------------------------------
    def mark_as_read(self, message_id: int, current_user: User) -> Message:
        """Mark the message as read for the current recipient."""

        message = self._get_message_for_user(message_id, current_user, mark_read=True)
        return message

    def get_unread_count(self, current_user: User) -> MessageUnreadCountResponse:
        statement = select(func.count(MessageRecipient.id)).where(
            MessageRecipient.recipient_user_id == current_user.id,
            MessageRecipient.is_read.is_(False),
        )
        unread_count = int(self.db.execute(statement).scalar_one())
        return MessageUnreadCountResponse(unread_count=unread_count)

    # Message retrieval ---------------------------------------------------
    def list_inbox(
        self,
        current_user: User,
        *,
        unread_only: bool = False,
        limit: int | None = None,
    ) -> list[MessageListItemResponse]:
        statement: Select[tuple[Message, MessageRecipient]] = (
            select(Message, MessageRecipient)
            .join(MessageRecipient, Message.id == MessageRecipient.message_id)
            .where(MessageRecipient.recipient_user_id == current_user.id)
        )
        if unread_only:
            statement = statement.where(MessageRecipient.is_read.is_(False))

        statement = statement.order_by(Message.created_at.desc(), Message.id.desc())
        if limit is not None:
            statement = statement.limit(limit)

        rows = list(self.db.execute(statement).all())
        if not rows:
            return []

        messages = [row[0] for row in rows]
        current_recipients_by_message_id = {row[0].id: row[1] for row in rows}
        recipients_by_message_id, users_by_id = self._prefetch_recipients_and_users(messages)

        return [
            self._build_list_item_response(
                message,
                recipients_by_message_id,
                users_by_id,
                current_recipient=current_recipients_by_message_id.get(message.id),
            )
            for message in messages
        ]

    def list_sent(
        self,
        current_user: User,
        *,
        limit: int | None = None,
    ) -> list[MessageListItemResponse]:
        statement: Select[tuple[Message]] = select(Message).where(
            Message.sender_user_id == current_user.id
        )
        statement = statement.order_by(Message.created_at.desc(), Message.id.desc())
        if limit is not None:
            statement = statement.limit(limit)

        messages = list(self.db.execute(statement).scalars().all())
        if not messages:
            return []

        recipients_by_message_id, users_by_id = self._prefetch_recipients_and_users(messages)
        return [
            self._build_list_item_response(
                message,
                recipients_by_message_id,
                users_by_id,
                current_recipient=None,
            )
            for message in messages
        ]

    def get_message(
        self,
        message_id: int,
        current_user: User,
        *,
        mark_read: bool = True,
    ) -> MessageResponse:
        message = self._get_message_for_user(message_id, current_user, mark_read=mark_read)
        recipients_by_message_id, users_by_id = self._prefetch_recipients_and_users([message])
        return self._build_message_response(message, recipients_by_message_id, users_by_id)

    # Templates -----------------------------------------------------------
    def create_template(
        self,
        owner: User,
        payload: MessageTemplateCreateRequest,
    ) -> MessageTemplate:
        template = MessageTemplate(
            owner_user_id=owner.id,
            name=payload.name,
            subject=payload.subject,
            body=payload.body,
            is_active=True,
        )
        self.db.add(template)
        return self._commit_and_refresh(
            template,
            conflict_message="Failed to create the template.",
        )

    def list_templates(self, owner: User) -> list[MessageTemplateResponse]:
        statement = (
            select(MessageTemplate)
            .where(MessageTemplate.owner_user_id == owner.id)
            .order_by(MessageTemplate.name.asc(), MessageTemplate.id.asc())
        )
        templates = list(self.db.execute(statement).scalars().all())
        return [MessageTemplateResponse.model_validate(template) for template in templates]

    def get_template(self, template_id: int, owner: User) -> MessageTemplate:
        template = self.db.execute(
            select(MessageTemplate)
            .where(
                MessageTemplate.id == template_id,
                MessageTemplate.owner_user_id == owner.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if template is None:
            raise MessagesNotFoundError("Template not found.")

        return template

    def update_template(
        self,
        template_id: int,
        owner: User,
        payload: MessageTemplateUpdateRequest,
    ) -> MessageTemplate:
        template = self.get_template(template_id, owner)
        changes = payload.model_dump(exclude_unset=True)
        for field_name, value in changes.items():
            setattr(template, field_name, value)

        self.db.add(template)
        return self._commit_and_refresh(
            template,
            conflict_message="Failed to update the template.",
        )

    def delete_template(self, template_id: int, owner: User) -> None:
        template = self.get_template(template_id, owner)
        self.db.delete(template)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise MessagesConflictError("Failed to delete the template.") from exc

    # Internal helpers ----------------------------------------------------
    def _get_message_for_user(
        self,
        message_id: int,
        current_user: User,
        *,
        mark_read: bool,
    ) -> Message:
        statement = select(Message).where(Message.id == message_id).limit(1)
        message = self.db.execute(statement).scalar_one_or_none()
        if message is None:
            raise MessagesNotFoundError("Message not found.")

        if message.sender_user_id != current_user.id:
            recipient_record = self.db.execute(
                select(MessageRecipient)
                .where(
                    MessageRecipient.message_id == message.id,
                    MessageRecipient.recipient_user_id == current_user.id,
                )
                .limit(1)
            ).scalar_one_or_none()
            if recipient_record is None:
                raise MessagesAuthorizationError("You are not allowed to view this message.")

            if mark_read and not recipient_record.is_read:
                recipient_record.is_read = True
                recipient_record.read_at = utcnow()
                self.db.add(recipient_record)
                self.db.commit()

        return message

    def _normalize_recipients(
        self, recipients: Iterable[MessageRecipientInput]
    ) -> list[_NormalizedRecipient]:
        normalized: list[_NormalizedRecipient] = []
        seen_user_ids: set[int] = set()
        for recipient in recipients:
            if recipient.user_id in seen_user_ids:
                continue

            user = self.db.get(User, recipient.user_id)
            if user is None or not user.is_active:
                raise MessagesValidationError("Recipient must reference an active user.")

            permission = (
                MessagePermissionEnum.CAN_REPLY
                if recipient.can_reply
                else MessagePermissionEnum.READ_ONLY
            )
            normalized.append(
                _NormalizedRecipient(
                    user_id=recipient.user_id,
                    permission=permission,
                )
            )
            seen_user_ids.add(recipient.user_id)

        if not normalized:
            raise MessagesValidationError("At least one recipient is required.")

        return normalized

    def _user_can_reply(self, message: Message, user: User) -> bool:
        if message.sender_user_id == user.id:
            return True

        recipient_record = self.db.execute(
            select(MessageRecipient)
            .where(
                MessageRecipient.message_id == message.id,
                MessageRecipient.recipient_user_id == user.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if recipient_record is None:
            return False

        return MessagePermissionEnum(recipient_record.permission) == MessagePermissionEnum.CAN_REPLY

    def _prefetch_recipients_and_users(
        self,
        messages: list[Message],
    ) -> tuple[dict[int, list[MessageRecipient]], dict[int, User]]:
        message_ids = [message.id for message in messages]
        if not message_ids:
            return {}, {}

        recipients = list(
            self.db.execute(
                select(MessageRecipient).where(MessageRecipient.message_id.in_(message_ids))
            )
            .scalars()
            .all()
        )

        recipients_by_message_id: dict[int, list[MessageRecipient]] = {}
        user_ids: set[int] = set()
        for recipient in recipients:
            recipients_by_message_id.setdefault(recipient.message_id, []).append(recipient)
            user_ids.add(recipient.recipient_user_id)

        sender_ids = {message.sender_user_id for message in messages}
        user_ids |= sender_ids

        users = list(
            self.db.execute(select(User).where(User.id.in_(user_ids)))
            .scalars()
            .all()
        )
        users_by_id = {user.id: user for user in users}
        return recipients_by_message_id, users_by_id

    def _build_message_response(
        self,
        message: Message,
        recipients_by_message_id: dict[int, list[MessageRecipient]],
        users_by_id: dict[int, User],
    ) -> MessageResponse:
        recipients = recipients_by_message_id.get(message.id, [])
        return MessageResponse(
            id=message.id,
            subject=message.subject,
            body=message.body,
            conversation_id=message.conversation_id or message.id,
            parent_message_id=message.parent_message_id,
            sender=self._build_user_summary(users_by_id.get(message.sender_user_id)),
            recipients=[
                self._build_recipient_response(recipient, users_by_id)
                for recipient in sorted(
                    recipients,
                    key=lambda item: (item.created_at, item.id),
                )
            ],
            created_at=message.created_at,
            updated_at=message.updated_at,
        )

    def _build_list_item_response(
        self,
        message: Message,
        recipients_by_message_id: dict[int, list[MessageRecipient]],
        users_by_id: dict[int, User],
        *,
        current_recipient: MessageRecipient | None,
    ) -> MessageListItemResponse:
        recipients = recipients_by_message_id.get(message.id, [])
        return MessageListItemResponse(
            id=message.id,
            subject=message.subject,
            conversation_id=message.conversation_id or message.id,
            parent_message_id=message.parent_message_id,
            sender=self._build_user_summary(users_by_id.get(message.sender_user_id)),
            recipients_count=len(recipients),
            is_read=current_recipient.is_read if current_recipient else True,
            can_reply=(
                MessagePermissionEnum(current_recipient.permission) == MessagePermissionEnum.CAN_REPLY
                if current_recipient
                else True
            ),
            created_at=message.created_at,
        )

    def _build_recipient_response(
        self,
        recipient: MessageRecipient,
        users_by_id: dict[int, User],
    ) -> MessageRecipientResponse:
        return MessageRecipientResponse(
            user=self._build_user_summary(users_by_id.get(recipient.recipient_user_id)),
            permission=MessagePermissionEnum(recipient.permission),
            is_read=recipient.is_read,
            read_at=recipient.read_at,
            created_at=recipient.created_at,
        )

    def _build_user_summary(self, user: User | None) -> UserSummary:
        if user is None:
            raise MessagesNotFoundError("User linked to the message could not be found.")

        full_name = " ".join(
            part.strip()
            for part in (user.first_name, user.last_name)
            if part and part.strip()
        ) or user.matricule

        return UserSummary(
            id=user.id,
            matricule=user.matricule,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=full_name,
        )

    def _send_notifications(
        self,
        message: Message,
        recipients: list[_NormalizedRecipient],
    ) -> None:
        snippet = (message.body or "").strip()
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."

        for recipient in recipients:
            if recipient.user_id == message.sender_user_id:
                continue

            self.notifications_service.create_notification(
                recipient_user_id=recipient.user_id,
                title=f"New message: {message.subject}",
                message=snippet or "You received a new message.",
                notification_type=NotificationTypeEnum.MESSAGE_RECEIVED,
                target_url=f"/messages/{message.id}",
            )

    def _commit_and_refresh(self, instance, *, conflict_message: str):
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise MessagesConflictError(conflict_message) from exc

        self.db.refresh(instance)
        return instance
