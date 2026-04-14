"""seed messages permission refactor codes

Revision ID: 2d4e6f8a9b1c
Revises: 1aa2bb3cc4dd
Create Date: 2026-04-14 12:00:00.000000
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2d4e6f8a9b1c"
down_revision = "1aa2bb3cc4dd"
branch_labels = None
depends_on = None


def upgrade() -> None:
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

    permissions_to_seed = (
        (
            "messages.read_users",
            "Read selectable message users",
            "List users that can be selected when composing a message.",
        ),
        (
            "messages.send_all",
            "Send messages to anyone",
            "Compose new messages targeting any active user.",
        ),
        (
            "messages.send_same_or_down",
            "Send messages to same or lower levels",
            "Compose new messages only for users on the same hierarchy level or below.",
        ),
        (
            "messages.reply",
            "Reply to messages",
            "Reply to accessible message threads without full send privileges.",
        ),
    )

    for code, name, description in permissions_to_seed:
        existing_id = bind.execute(
            sa.select(permissions_table.c.id)
            .where(permissions_table.c.code == code)
            .limit(1)
        ).scalar_one_or_none()

        if existing_id is None:
            bind.execute(
                sa.insert(permissions_table).values(
                    code=code,
                    name=name,
                    description=description,
                    module="messages",
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
                    name=name,
                    description=description,
                    module="messages",
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
    bind.execute(
        sa.delete(permissions_table).where(
            permissions_table.c.code.in_(
                [
                    "messages.read_users",
                    "messages.send_all",
                    "messages.send_same_or_down",
                    "messages.reply",
                ]
            )
        )
    )
