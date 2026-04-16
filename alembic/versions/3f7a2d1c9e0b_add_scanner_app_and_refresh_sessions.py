"""add scanner app metadata and auth refresh sessions

Revision ID: 3f7a2d1c9e0b
Revises: 2d4e6f8a9b1c
Create Date: 2026-04-15 23:55:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3f7a2d1c9e0b"
down_revision = "2d4e6f8a9b1c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "allowed_origins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("origin", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_allowed_origins")),
        sa.UniqueConstraint("origin", name=op.f("uq_allowed_origins_origin")),
    )
    op.create_index(op.f("ix_allowed_origins_origin"), "allowed_origins", ["origin"], unique=True)
    op.create_index(op.f("ix_allowed_origins_is_active"), "allowed_origins", ["is_active"], unique=False)

    op.create_table(
        "scanner_app_builds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("target_name", sa.String(length=120), nullable=False),
        sa.Column("backend_base_url", sa.String(length=255), nullable=False),
        sa.Column("allowed_origin", sa.String(length=255), nullable=True),
        sa.Column("android_download_url", sa.String(length=500), nullable=True),
        sa.Column("windows_download_url", sa.String(length=500), nullable=True),
        sa.Column("linux_download_url", sa.String(length=500), nullable=True),
        sa.Column("generated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scanner_app_builds")),
    )
    op.create_index(
        op.f("ix_scanner_app_builds_generated_by_user_id"),
        "scanner_app_builds",
        ["generated_by_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_scanner_app_builds_is_active"), "scanner_app_builds", ["is_active"], unique=False)
    op.create_index(op.f("ix_scanner_app_builds_created_at"), "scanner_app_builds", ["created_at"], unique=False)

    op.create_table(
        "auth_refresh_token_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_refresh_token_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_refresh_token_sessions_token_hash")),
    )
    op.create_index(
        op.f("ix_auth_refresh_token_sessions_user_id"),
        "auth_refresh_token_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_auth_refresh_token_sessions_token_hash"),
        "auth_refresh_token_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_auth_refresh_token_sessions_device_id"),
        "auth_refresh_token_sessions",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_auth_refresh_token_sessions_expires_at"),
        "auth_refresh_token_sessions",
        ["expires_at"],
        unique=False,
    )

    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.Integer()),
        sa.column("code", sa.String(length=100)),
        sa.column("name", sa.String(length=120)),
        sa.column("description", sa.Text()),
        sa.column("module", sa.String(length=50)),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    code = "attendance.nfc.ingest"
    existing_id = bind.execute(
        sa.select(permissions_table.c.id).where(permissions_table.c.code == code).limit(1)
    ).scalar_one_or_none()
    if existing_id is None:
        bind.execute(
            sa.insert(permissions_table).values(
                code=code,
                name="Ingest NFC attendance events",
                description="Submit NFC scan events from the dedicated scanner application.",
                module="attendance",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        bind.execute(
            sa.update(permissions_table)
            .where(permissions_table.c.id == existing_id)
            .values(
                name="Ingest NFC attendance events",
                description="Submit NFC scan events from the dedicated scanner application.",
                module="attendance",
                is_active=True,
                updated_at=now,
            )
        )


def downgrade() -> None:
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.Integer()),
        sa.column("code", sa.String(length=100)),
    )
    bind = op.get_bind()
    bind.execute(sa.delete(permissions_table).where(permissions_table.c.code == "attendance.nfc.ingest"))

    op.drop_index(op.f("ix_auth_refresh_token_sessions_expires_at"), table_name="auth_refresh_token_sessions")
    op.drop_index(op.f("ix_auth_refresh_token_sessions_device_id"), table_name="auth_refresh_token_sessions")
    op.drop_index(op.f("ix_auth_refresh_token_sessions_token_hash"), table_name="auth_refresh_token_sessions")
    op.drop_index(op.f("ix_auth_refresh_token_sessions_user_id"), table_name="auth_refresh_token_sessions")
    op.drop_table("auth_refresh_token_sessions")

    op.drop_index(op.f("ix_scanner_app_builds_created_at"), table_name="scanner_app_builds")
    op.drop_index(op.f("ix_scanner_app_builds_is_active"), table_name="scanner_app_builds")
    op.drop_index(op.f("ix_scanner_app_builds_generated_by_user_id"), table_name="scanner_app_builds")
    op.drop_table("scanner_app_builds")

    op.drop_index(op.f("ix_allowed_origins_is_active"), table_name="allowed_origins")
    op.drop_index(op.f("ix_allowed_origins_origin"), table_name="allowed_origins")
    op.drop_table("allowed_origins")
