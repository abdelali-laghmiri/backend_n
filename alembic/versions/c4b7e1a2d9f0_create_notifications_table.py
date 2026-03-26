"""create notifications table

Revision ID: c4b7e1a2d9f0
Revises: a6b1f5d3c9e2
Create Date: 2026-03-26 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4b7e1a2d9f0"
down_revision = "a6b1f5d3c9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_url", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_notifications_recipient_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notifications_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_is_read"),
            ["is_read"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_recipient_user_id"),
            ["recipient_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_type"),
            ["type"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notifications_type"))
        batch_op.drop_index(batch_op.f("ix_notifications_recipient_user_id"))
        batch_op.drop_index(batch_op.f("ix_notifications_is_read"))
        batch_op.drop_index(batch_op.f("ix_notifications_created_at"))

    op.drop_table("notifications")
