from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps.announcements.models import (
    Announcement,
    AnnouncementAttachment,
    AnnouncementRead,
    AnnouncementTypeEnum,
    utcnow,
)
from app.apps.announcements.storage import build_announcement_attachment_access_url
from app.apps.announcements.schemas import (
    AnnouncementAttachmentResponse,
    AnnouncementCreateRequest,
    AnnouncementDetailResponse,
    AnnouncementListItemResponse,
    AnnouncementMarkSeenResponse,
    AnnouncementUpdateRequest,
    AnnouncementUserSummary,
)
from app.apps.users.models import User
from app.shared.uploads import StoredUploadFile


class AnnouncementsConflictError(RuntimeError):
    """Raised when a persistence conflict prevents an announcement operation."""


class AnnouncementsNotFoundError(RuntimeError):
    """Raised when an announcement or attachment record cannot be found."""


class AnnouncementsValidationError(RuntimeError):
    """Raised when an announcement request is invalid."""


@dataclass(slots=True)
class _AnnouncementResponseContext:
    """Prefetched read and attachment data used to build API responses efficiently."""

    reads_by_announcement_id: dict[int, AnnouncementRead]
    attachment_counts_by_announcement_id: dict[int, int]
    attachments_by_announcement_id: dict[int, list[AnnouncementAttachment]]
    users_by_id: dict[int, User]


class AnnouncementsService:
    """Service layer for company-wide announcements, attachments, and read tracking."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_announcements(
        self,
        current_user: User,
        *,
        include_all: bool = False,
        limit: int | None = None,
    ) -> list[Announcement]:
        """List announcements for either the public feed or the management view."""

        statement: Select[tuple[Announcement]] = select(Announcement)
        if not include_all:
            statement = statement.where(*self._build_visible_conditions())

        statement = statement.order_by(
            Announcement.is_pinned.desc(),
            self._announcement_type_priority(),
            Announcement.published_at.desc(),
            Announcement.id.desc(),
        )

        if limit is not None:
            statement = statement.limit(limit)

        announcements = list(self.db.execute(statement).scalars().all())
        return announcements

    def get_announcement_for_user(
        self,
        announcement_id: int,
        current_user: User,
        *,
        include_all: bool = False,
    ) -> Announcement:
        """Return one announcement with either public-visibility or management rules."""

        statement = select(Announcement).where(Announcement.id == announcement_id)
        if not include_all:
            statement = statement.where(*self._build_visible_conditions())

        announcement = self.db.execute(statement.limit(1)).scalar_one_or_none()
        if announcement is None:
            raise AnnouncementsNotFoundError("Announcement not found.")

        return announcement

    def create_announcement(
        self,
        payload: AnnouncementCreateRequest,
        current_user: User,
    ) -> Announcement:
        """Create one announcement record."""

        self._validate_schedule(payload.published_at, payload.expires_at)

        announcement = Announcement(
            title=payload.title,
            summary=payload.summary,
            content=payload.content,
            type=payload.type.value,
            is_pinned=payload.is_pinned,
            is_active=payload.is_active,
            published_at=payload.published_at,
            expires_at=payload.expires_at,
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
        )
        self.db.add(announcement)
        return self._commit_and_refresh(
            announcement,
            conflict_message="Failed to create the announcement.",
        )

    def update_announcement(
        self,
        announcement_id: int,
        payload: AnnouncementUpdateRequest,
        current_user: User,
    ) -> Announcement:
        """Fully update one announcement record."""

        announcement = self._get_announcement(announcement_id)
        self._validate_schedule(payload.published_at, payload.expires_at)

        announcement.title = payload.title
        announcement.summary = payload.summary
        announcement.content = payload.content
        announcement.type = payload.type.value
        announcement.is_pinned = payload.is_pinned
        announcement.is_active = payload.is_active
        announcement.published_at = payload.published_at
        announcement.expires_at = payload.expires_at
        announcement.updated_by_user_id = current_user.id

        self.db.add(announcement)
        return self._commit_and_refresh(
            announcement,
            conflict_message="Failed to update the announcement.",
        )

    def deactivate_announcement(
        self,
        announcement_id: int,
        current_user: User,
    ) -> None:
        """Soft-delete one announcement by deactivating it."""

        announcement = self._get_announcement(announcement_id)
        if not announcement.is_active:
            return

        announcement.is_active = False
        announcement.updated_by_user_id = current_user.id
        self.db.add(announcement)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AnnouncementsConflictError(
                "Failed to delete the announcement."
            ) from exc

    def add_attachments(
        self,
        announcement_id: int,
        current_user: User,
        uploads: list[StoredUploadFile],
    ) -> Announcement:
        """Persist attachment metadata for an announcement after files are stored."""

        if not uploads:
            raise AnnouncementsValidationError("At least one attachment file is required.")

        announcement = self._get_announcement(announcement_id)
        announcement.updated_by_user_id = current_user.id
        self.db.add(announcement)

        for upload in uploads:
            attachment = AnnouncementAttachment(
                announcement_id=announcement.id,
                original_file_name=upload.original_file_name,
                stored_file_name=upload.stored_file_name,
                file_url=upload.file_url,
                content_type=upload.content_type,
                file_extension=upload.file_extension,
                file_size_bytes=upload.file_size_bytes,
                uploaded_by_user_id=current_user.id,
            )
            self.db.add(attachment)

        return self._commit_and_refresh(
            announcement,
            conflict_message="Failed to attach files to the announcement.",
        )

    def get_attachment_for_user(
        self,
        announcement_id: int,
        attachment_id: int,
        current_user: User,
        *,
        include_all: bool = False,
    ) -> AnnouncementAttachment:
        """Return one attachment when its parent announcement is visible to the user."""

        announcement = self.get_announcement_for_user(
            announcement_id,
            current_user,
            include_all=include_all,
        )
        attachment = self.db.execute(
            select(AnnouncementAttachment)
            .where(
                AnnouncementAttachment.id == attachment_id,
                AnnouncementAttachment.announcement_id == announcement.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if attachment is None:
            raise AnnouncementsNotFoundError("Announcement attachment not found.")

        return attachment

    def remove_attachment(
        self,
        announcement_id: int,
        attachment_id: int,
        current_user: User,
    ) -> str:
        """Delete one attachment record and return the managed file URL for cleanup."""

        announcement = self._get_announcement(announcement_id)
        attachment = self.db.execute(
            select(AnnouncementAttachment)
            .where(
                AnnouncementAttachment.id == attachment_id,
                AnnouncementAttachment.announcement_id == announcement.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if attachment is None:
            raise AnnouncementsNotFoundError("Announcement attachment not found.")

        file_url = attachment.file_url
        announcement.updated_by_user_id = current_user.id
        self.db.add(announcement)
        self.db.delete(attachment)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AnnouncementsConflictError(
                "Failed to delete the announcement attachment."
            ) from exc

        return file_url

    def mark_seen(
        self,
        announcement_id: int,
        current_user: User,
    ) -> AnnouncementRead:
        """Create one read-tracking row for the authenticated user if needed."""

        self.get_announcement_for_user(announcement_id, current_user, include_all=False)

        read_record = self.db.execute(
            select(AnnouncementRead)
            .where(
                AnnouncementRead.announcement_id == announcement_id,
                AnnouncementRead.user_id == current_user.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if read_record is not None:
            return read_record

        read_record = AnnouncementRead(
            announcement_id=announcement_id,
            user_id=current_user.id,
            seen_at=utcnow(),
        )
        self.db.add(read_record)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            read_record = self.db.execute(
                select(AnnouncementRead)
                .where(
                    AnnouncementRead.announcement_id == announcement_id,
                    AnnouncementRead.user_id == current_user.id,
                )
                .limit(1)
            ).scalar_one_or_none()
            if read_record is not None:
                return read_record

            raise AnnouncementsConflictError(
                "Failed to mark the announcement as seen."
            ) from exc

        self.db.refresh(read_record)
        return read_record

    def build_announcement_list_responses(
        self,
        announcements: list[Announcement],
        current_user: User,
    ) -> list[AnnouncementListItemResponse]:
        """Build list responses with read state, attachments, and author metadata."""

        context = self._prefetch_response_context(announcements, current_user.id)
        return [
            self._build_list_item_response(announcement, context)
            for announcement in announcements
        ]

    def build_announcement_detail_response(
        self,
        announcement: Announcement,
        current_user: User,
    ) -> AnnouncementDetailResponse:
        """Build the detail response for one announcement."""

        context = self._prefetch_response_context([announcement], current_user.id)
        read_record = context.reads_by_announcement_id.get(announcement.id)
        attachments = context.attachments_by_announcement_id.get(announcement.id, [])
        return AnnouncementDetailResponse(
            id=announcement.id,
            title=announcement.title,
            summary=announcement.summary,
            content=announcement.content,
            type=AnnouncementTypeEnum(announcement.type),
            is_pinned=announcement.is_pinned,
            is_active=announcement.is_active,
            is_currently_visible=self._is_currently_visible(announcement),
            published_at=self._normalize_datetime(announcement.published_at),
            expires_at=self._normalize_datetime(announcement.expires_at),
            is_seen=read_record is not None,
            seen_at=(
                self._normalize_datetime(read_record.seen_at)
                if read_record is not None
                else None
            ),
            has_attachments=bool(attachments),
            attachments_count=len(attachments),
            attachments=[
                self._build_attachment_response(attachment) for attachment in attachments
            ],
            created_at=self._normalize_datetime(announcement.created_at),
            updated_at=self._normalize_datetime(announcement.updated_at),
            created_by=self._build_user_summary(
                context.users_by_id[announcement.created_by_user_id]
            ),
            updated_by=self._build_user_summary(
                context.users_by_id[announcement.updated_by_user_id]
            ),
        )

    def build_mark_seen_response(
        self,
        read_record: AnnouncementRead,
    ) -> AnnouncementMarkSeenResponse:
        """Build the response payload for idempotent mark-seen operations."""

        return AnnouncementMarkSeenResponse(
            announcement_id=read_record.announcement_id,
            is_seen=True,
            seen_at=self._normalize_datetime(read_record.seen_at),
        )

    def _get_announcement(self, announcement_id: int) -> Announcement:
        """Return an announcement by id regardless of public visibility."""

        announcement = self.db.get(Announcement, announcement_id)
        if announcement is None:
            raise AnnouncementsNotFoundError("Announcement not found.")

        return announcement

    def _build_visible_conditions(self):
        """Return the SQLAlchemy visibility rules for end-user reads."""

        now = utcnow()
        return (
            Announcement.is_active.is_(True),
            Announcement.published_at <= now,
            or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
        )

    def _announcement_type_priority(self):
        """Return the ordering priority used by list endpoints."""

        return case(
            (Announcement.type == AnnouncementTypeEnum.MANDATORY.value, 0),
            (Announcement.type == AnnouncementTypeEnum.IMPORTANT.value, 1),
            (Announcement.type == AnnouncementTypeEnum.INFO.value, 2),
            else_=3,
        )

    def _prefetch_response_context(
        self,
        announcements: list[Announcement],
        current_user_id: int,
    ) -> _AnnouncementResponseContext:
        """Prefetch related data needed to build announcement responses."""

        announcement_ids = [announcement.id for announcement in announcements]
        if not announcement_ids:
            return _AnnouncementResponseContext(
                reads_by_announcement_id={},
                attachment_counts_by_announcement_id={},
                attachments_by_announcement_id={},
                users_by_id={},
            )

        reads = list(
            self.db.execute(
                select(AnnouncementRead).where(
                    AnnouncementRead.announcement_id.in_(announcement_ids),
                    AnnouncementRead.user_id == current_user_id,
                )
            )
            .scalars()
            .all()
        )
        reads_by_announcement_id = {
            read_record.announcement_id: read_record for read_record in reads
        }

        attachment_rows = self.db.execute(
            select(
                AnnouncementAttachment.announcement_id,
                func.count(AnnouncementAttachment.id),
            )
            .where(AnnouncementAttachment.announcement_id.in_(announcement_ids))
            .group_by(AnnouncementAttachment.announcement_id)
        ).all()
        attachment_counts_by_announcement_id = {
            announcement_id: int(count)
            for announcement_id, count in attachment_rows
        }

        attachments = list(
            self.db.execute(
                select(AnnouncementAttachment)
                .where(AnnouncementAttachment.announcement_id.in_(announcement_ids))
                .order_by(
                    AnnouncementAttachment.created_at.asc(),
                    AnnouncementAttachment.id.asc(),
                )
            )
            .scalars()
            .all()
        )
        attachments_by_announcement_id: dict[int, list[AnnouncementAttachment]] = {}
        for attachment in attachments:
            attachments_by_announcement_id.setdefault(
                attachment.announcement_id,
                [],
            ).append(attachment)

        user_ids = {
            announcement.created_by_user_id
            for announcement in announcements
        } | {
            announcement.updated_by_user_id
            for announcement in announcements
        }
        users = list(
            self.db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
        )
        users_by_id = {user.id: user for user in users}

        return _AnnouncementResponseContext(
            reads_by_announcement_id=reads_by_announcement_id,
            attachment_counts_by_announcement_id=attachment_counts_by_announcement_id,
            attachments_by_announcement_id=attachments_by_announcement_id,
            users_by_id=users_by_id,
        )

    def _build_list_item_response(
        self,
        announcement: Announcement,
        context: _AnnouncementResponseContext,
    ) -> AnnouncementListItemResponse:
        """Build one list-item response."""

        read_record = context.reads_by_announcement_id.get(announcement.id)
        attachments_count = context.attachment_counts_by_announcement_id.get(
            announcement.id,
            0,
        )

        return AnnouncementListItemResponse(
            id=announcement.id,
            title=announcement.title,
            summary=announcement.summary,
            type=AnnouncementTypeEnum(announcement.type),
            is_pinned=announcement.is_pinned,
            is_active=announcement.is_active,
            is_currently_visible=self._is_currently_visible(announcement),
            published_at=self._normalize_datetime(announcement.published_at),
            expires_at=self._normalize_datetime(announcement.expires_at),
            is_seen=read_record is not None,
            seen_at=(
                self._normalize_datetime(read_record.seen_at)
                if read_record is not None
                else None
            ),
            has_attachments=attachments_count > 0,
            attachments_count=attachments_count,
            created_at=self._normalize_datetime(announcement.created_at),
            updated_at=self._normalize_datetime(announcement.updated_at),
            created_by=self._build_user_summary(
                context.users_by_id[announcement.created_by_user_id]
            ),
        )

    def _build_attachment_response(
        self,
        attachment: AnnouncementAttachment,
    ) -> AnnouncementAttachmentResponse:
        """Build one attachment response payload."""

        return AnnouncementAttachmentResponse(
            id=attachment.id,
            file_name=attachment.original_file_name,
            file_url=build_announcement_attachment_access_url(
                attachment.announcement_id,
                attachment.id,
            ),
            content_type=attachment.content_type,
            file_extension=attachment.file_extension,
            file_size_bytes=attachment.file_size_bytes,
            created_at=self._normalize_datetime(attachment.created_at),
        )

    def _build_user_summary(self, user: User) -> AnnouncementUserSummary:
        """Build a compact user summary for author/editor metadata."""

        full_name = " ".join(
            part.strip()
            for part in (user.first_name, user.last_name)
            if part and part.strip()
        ) or user.matricule
        return AnnouncementUserSummary(
            id=user.id,
            matricule=user.matricule,
            first_name=user.first_name,
            last_name=user.last_name,
            full_name=full_name,
        )

    def _is_currently_visible(self, announcement: Announcement) -> bool:
        """Return whether an announcement is currently visible in the public feed."""

        now = utcnow()
        if not announcement.is_active:
            return False

        published_at = self._normalize_datetime(announcement.published_at)
        expires_at = self._normalize_datetime(announcement.expires_at)

        if published_at > now:
            return False

        if expires_at is not None and expires_at <= now:
            return False

        return True

    def _normalize_datetime(self, value: datetime | None) -> datetime | None:
        """Normalize stored datetimes because SQLite can return naive values."""

        if value is None:
            return None

        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    def _validate_schedule(
        self,
        published_at,
        expires_at,
    ) -> None:
        """Validate announcement publish and expiry chronology."""

        if expires_at is not None and expires_at <= published_at:
            raise AnnouncementsValidationError(
                "expires_at must be later than published_at."
            )

    def _commit_and_refresh(
        self,
        announcement: Announcement,
        *,
        conflict_message: str,
    ) -> Announcement:
        """Commit the transaction and refresh the target announcement."""

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AnnouncementsConflictError(conflict_message) from exc

        self.db.refresh(announcement)
        return announcement
