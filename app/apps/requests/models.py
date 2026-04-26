from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class RequestFieldTypeEnum(str, Enum):
    """Supported dynamic request-field input types."""

    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    SELECT = "select"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"


class RequestStepKindEnum(str, Enum):
    """Supported workflow step kinds."""

    APPROVER = "approver"
    CONCEPTION = "conception"


class RequestResolverTypeEnum(str, Enum):
    """Supported workflow approver resolvers."""

    TEAM_LEADER = "TEAM_LEADER"
    DEPARTMENT_MANAGER = "DEPARTMENT_MANAGER"
    RH_MANAGER = "RH_MANAGER"


class RequestStatusEnum(str, Enum):
    """Supported request lifecycle statuses."""

    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"


class RequestActionEnum(str, Enum):
    """Supported workflow history actions."""

    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    COMPLETED = "completed"


class RequestType(Base):
    """Configurable request type definition."""

    __tablename__ = "request_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class RequestTypeField(Base):
    """Dynamic field definition attached to a request type."""

    __tablename__ = "request_type_fields"
    __table_args__ = (
        UniqueConstraint(
            "request_type_id",
            "code",
            name="uq_request_type_fields_request_type_code",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_type_id: Mapped[int] = mapped_column(
        ForeignKey("request_types.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    placeholder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_value: Mapped[object | None] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class RequestWorkflowStep(Base):
    """Dynamic workflow step definition attached to a request type."""

    __tablename__ = "request_workflow_steps"
    __table_args__ = (
        UniqueConstraint(
            "request_type_id",
            "step_order",
            name="uq_request_workflow_steps_request_type_step_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_type_id: Mapped[int] = mapped_column(
        ForeignKey("request_types.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    step_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    resolver_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolver_job_title_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_titles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class WorkflowRequest(Base):
    """Submitted request instance flowing through a configured workflow."""

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_type_id: Mapped[int] = mapped_column(
        ForeignKey("request_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    requester_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    requester_employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    current_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("request_workflow_steps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    current_approver_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class RequestFieldValue(Base):
    """Submitted field value snapshot stored with a request."""

    __tablename__ = "request_field_values"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "field_code",
            name="uq_request_field_values_request_field_code",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_field_id: Mapped[int | None] = mapped_column(
        ForeignKey("request_type_fields.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    field_code: Mapped[str] = mapped_column(String(100), nullable=False)
    field_label: Mapped[str] = mapped_column(String(120), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    value: Mapped[object | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


class RequestActionHistory(Base):
    """Workflow traceability entry for request lifecycle actions."""

    __tablename__ = "request_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[int | None] = mapped_column(
        ForeignKey("request_workflow_steps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    step_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    step_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolver_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )


__all__ = [
    "RequestActionEnum",
    "RequestActionHistory",
    "RequestFieldTypeEnum",
    "RequestFieldValue",
    "RequestResolverTypeEnum",
    "RequestStatusEnum",
    "RequestStepKindEnum",
    "RequestType",
    "RequestTypeField",
    "RequestWorkflowStep",
    "WorkflowRequest",
]
