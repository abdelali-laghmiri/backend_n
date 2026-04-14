from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.employees.models import Employee
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
    MessageRecipientCandidateResponse,
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
from app.apps.organization.models import Department, JobTitle, Team
from app.apps.permissions.service import PermissionsService
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


@dataclass(frozen=True)
class _MessagingAccessPolicy:
    can_read_users: bool
    can_send_all: bool
    can_send_same_or_down: bool
    can_reply: bool
    has_legacy_send: bool

    @property
    def can_initiate(self) -> bool:
        return self.can_send_all or self.can_send_same_or_down or self.has_legacy_send

    @property
    def can_send_to_anyone(self) -> bool:
        return self.can_send_all or self.has_legacy_send

    @property
    def can_reply_in_thread(self) -> bool:
        return self.can_reply or self.can_initiate


class MessagesService:
    """Service layer for internal mail messages and templates."""

    def __init__(
        self,
        db: Session,
        notifications_service: NotificationsService,
        permissions_service: PermissionsService,
    ) -> None:
        self.db = db
        self.notifications_service = notifications_service
        self.permissions_service = permissions_service

    # Message composition -------------------------------------------------
    def send_message(self, sender: User, payload: MessageCreateRequest) -> Message:
        """Compose a new message or reply and deliver to recipients."""

        access_policy = self._get_access_policy(sender)
        recipients = self._normalize_recipients(payload.recipients)

        parent_message = None
        conversation_id = None
        if payload.parent_message_id is not None:
            if not access_policy.can_reply_in_thread:
                raise MessagesAuthorizationError(
                    "You do not have permission to reply to messages."
                )

            parent_message = self._get_message_for_user(
                payload.parent_message_id,
                sender,
                mark_read=False,
            )
            if not self._user_can_reply(parent_message, sender):
                raise MessagesAuthorizationError("You cannot reply to this message.")

            conversation_id = parent_message.conversation_id or parent_message.id
        elif not access_policy.can_initiate:
            raise MessagesAuthorizationError(
                "You do not have permission to send new messages."
            )

        self._ensure_recipients_allowed(
            sender,
            recipients,
            access_policy=access_policy,
            parent_message=parent_message,
        )

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

    def list_available_recipients(
        self,
        current_user: User,
        *,
        q: str | None = None,
        limit: int | None = None,
    ) -> list[MessageRecipientCandidateResponse]:
        access_policy = self._get_access_policy(current_user)
        if not access_policy.can_read_users:
            raise MessagesAuthorizationError("Permission 'messages.read_users' is required.")

        if access_policy.can_send_to_anyone:
            scoped_user_ids: set[int] | None = None
        elif access_policy.can_send_same_or_down:
            scoped_user_ids = self._get_same_or_down_user_ids(current_user)
            if not scoped_user_ids:
                return []
        else:
            return []

        statement = (
            select(
                User.id,
                User.matricule,
                User.first_name,
                User.last_name,
                Department.name.label("department"),
                Team.name.label("team"),
                JobTitle.name.label("job_title"),
                JobTitle.hierarchical_level.label("hierarchical_level"),
            )
            .select_from(User)
            .outerjoin(
                Employee,
                and_(
                    Employee.user_id == User.id,
                    Employee.is_active.is_(True),
                ),
            )
            .outerjoin(
                JobTitle,
                and_(
                    JobTitle.id == Employee.job_title_id,
                    JobTitle.is_active.is_(True),
                ),
            )
            .outerjoin(Department, Department.id == Employee.department_id)
            .outerjoin(Team, Team.id == Employee.team_id)
            .where(User.is_active.is_(True))
        )

        if scoped_user_ids is not None:
            statement = statement.where(User.id.in_(scoped_user_ids))

        normalized_query = q.strip() if q is not None else ""
        if normalized_query:
            search_value = f"%{normalized_query}%"
            statement = statement.where(
                or_(
                    User.matricule.ilike(search_value),
                    User.first_name.ilike(search_value),
                    User.last_name.ilike(search_value),
                    Department.name.ilike(search_value),
                    Team.name.ilike(search_value),
                    JobTitle.name.ilike(search_value),
                )
            )

        statement = statement.order_by(
            User.first_name.asc(),
            User.last_name.asc(),
            User.matricule.asc(),
        )
        if limit is not None:
            statement = statement.limit(limit)

        rows = self.db.execute(statement).all()
        candidates: list[MessageRecipientCandidateResponse] = []
        for row in rows:
            full_name = " ".join(
                part.strip()
                for part in (row.first_name, row.last_name)
                if part and part.strip()
            ) or row.matricule
            candidates.append(
                MessageRecipientCandidateResponse(
                    id=row.id,
                    matricule=row.matricule,
                    first_name=row.first_name,
                    last_name=row.last_name,
                    full_name=full_name,
                    department=row.department,
                    team=row.team,
                    job_title=row.job_title,
                    hierarchical_level=row.hierarchical_level,
                )
            )

        return candidates

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

    def _get_access_policy(self, user: User) -> _MessagingAccessPolicy:
        return _MessagingAccessPolicy(
            can_read_users=self.permissions_service.user_has_permission(
                user,
                "messages.read_users",
            )
            or self.permissions_service.user_has_permission(user, "messages.send"),
            can_send_all=self.permissions_service.user_has_permission(
                user,
                "messages.send_all",
            ),
            can_send_same_or_down=self.permissions_service.user_has_permission(
                user,
                "messages.send_same_or_down",
            ),
            can_reply=self.permissions_service.user_has_permission(user, "messages.reply"),
            has_legacy_send=self.permissions_service.user_has_permission(
                user,
                "messages.send",
            ),
        )

    def _ensure_recipients_allowed(
        self,
        sender: User,
        recipients: list[_NormalizedRecipient],
        *,
        access_policy: _MessagingAccessPolicy,
        parent_message: Message | None,
    ) -> None:
        recipient_ids = {recipient.user_id for recipient in recipients}
        if not recipient_ids:
            return

        if access_policy.can_send_to_anyone:
            return

        if access_policy.can_send_same_or_down:
            allowed_user_ids = self._get_same_or_down_user_ids(sender)
            disallowed_user_ids = sorted(recipient_ids - allowed_user_ids)
            if disallowed_user_ids:
                raise MessagesAuthorizationError(
                    "You can only message users from the same hierarchy level or below."
                )
            return

        if parent_message is not None and access_policy.can_reply:
            participant_user_ids = self._get_conversation_participant_user_ids(
                parent_message
            )
            disallowed_user_ids = sorted(recipient_ids - participant_user_ids)
            if disallowed_user_ids:
                raise MessagesAuthorizationError(
                    "Reply recipients must belong to the current conversation participants."
                )
            return

        raise MessagesAuthorizationError("You do not have permission to send messages.")

    def _get_same_or_down_user_ids(self, sender: User) -> set[int]:
        sender_level = self._get_user_hierarchical_level(sender.id)
        if sender_level is None:
            raise MessagesAuthorizationError(
                "Your hierarchy level could not be resolved for messaging scope."
            )

        statement = (
            select(Employee.user_id)
            .select_from(Employee)
            .join(User, User.id == Employee.user_id)
            .join(JobTitle, JobTitle.id == Employee.job_title_id)
            .where(
                Employee.is_active.is_(True),
                User.is_active.is_(True),
                JobTitle.is_active.is_(True),
                JobTitle.hierarchical_level <= sender_level,
            )
        )
        return set(self.db.execute(statement).scalars().all())

    def _get_user_hierarchical_level(self, user_id: int) -> int | None:
        statement = (
            select(JobTitle.hierarchical_level)
            .select_from(Employee)
            .join(JobTitle, JobTitle.id == Employee.job_title_id)
            .where(
                Employee.user_id == user_id,
                Employee.is_active.is_(True),
                JobTitle.is_active.is_(True),
            )
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def _get_conversation_participant_user_ids(self, message: Message) -> set[int]:
        conversation_id = message.conversation_id or message.id
        message_rows = self.db.execute(
            select(Message.id, Message.sender_user_id).where(
                or_(
                    Message.conversation_id == conversation_id,
                    Message.id == conversation_id,
                )
            )
        ).all()

        if not message_rows:
            return {message.sender_user_id}

        message_ids = [row.id for row in message_rows]
        participant_user_ids = {row.sender_user_id for row in message_rows}
        recipient_user_ids = self.db.execute(
            select(MessageRecipient.recipient_user_id).where(
                MessageRecipient.message_id.in_(message_ids)
            )
        ).scalars()
        participant_user_ids.update(recipient_user_ids)
        return participant_user_ids

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
