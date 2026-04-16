from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AllowedOrigin(Base):
    """Database-managed browser origin allow list entry."""

    __tablename__ = "allowed_origins"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    origin: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
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


class ScannerAppBuild(Base):
    """Generated scanner app distribution metadata for one backend target."""

    __tablename__ = "scanner_app_builds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target_name: Mapped[str] = mapped_column(String(120), nullable=False)
    backend_base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    allowed_origin: Mapped[str | None] = mapped_column(String(255), nullable=True)
    android_download_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    windows_download_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linux_download_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generated_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


__all__ = ["AllowedOrigin", "ScannerAppBuild"]
