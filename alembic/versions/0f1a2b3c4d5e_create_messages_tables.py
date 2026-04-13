"""create messages tables

Revision ID: 0f1a2b3c4d5e
Revises: 8f2c6d1a4b7e
Create Date: 2026-04-13 12:00:00.000000
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0f1a2b3c4d5e"
down_revision = "8f2c6d1a4b7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("parent_message_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sender_user_id"],
            ["users.id"],
            name=op.f("fk_messages_sender_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["messages.id"],
            name=op.f("fk_messages_conversation_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_message_id"],
            ["messages.id"],
            name=op.f("fk_messages_parent_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_messages_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_messages_sender_user_id"), ["sender_user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_messages_conversation_id"), ["conversation_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_messages_parent_message_id"), ["parent_message_id"], unique=False)

    op.create_table(
        "message_recipients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("permission", sa.String(length=20), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_message_recipients_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_message_recipients_recipient_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_recipients")),
        sa.UniqueConstraint(
            "message_id",
            "recipient_user_id",
            name="uq_message_recipients_message_recipient",
        ),
    )
    with op.batch_alter_table("message_recipients", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_message_recipients_message_id"), ["message_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_message_recipients_recipient_user_id"),
            ["recipient_user_id"],
            unique=False,
        )
        batch_op.create_index(batch_op.f("ix_message_recipients_permission"), ["permission"], unique=False)
        batch_op.create_index(batch_op.f("ix_message_recipients_is_read"), ["is_read"], unique=False)
        batch_op.create_index(batch_op.f("ix_message_recipients_created_at"), ["created_at"], unique=False)

    op.create_table(
        "message_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_message_templates_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_templates")),
    )
    with op.batch_alter_table("message_templates", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_message_templates_owner_user_id"), ["owner_user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_message_templates_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_message_templates_created_at"), ["created_at"], unique=False)

    _seed_permissions()


def downgrade() -> None:
    _delete_seeded_permissions()

    with op.batch_alter_table("message_templates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_message_templates_created_at"))
        batch_op.drop_index(batch_op.f("ix_message_templates_is_active"))
        batch_op.drop_index(batch_op.f("ix_message_templates_owner_user_id"))
    op.drop_table("message_templates")

    with op.batch_alter_table("message_recipients", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_message_recipients_created_at"))
        batch_op.drop_index(batch_op.f("ix_message_recipients_is_read"))
        batch_op.drop_index(batch_op.f("ix_message_recipients_permission"))
        batch_op.drop_index(batch_op.f("ix_message_recipients_recipient_user_id"))
        batch_op.drop_index(batch_op.f("ix_message_recipients_message_id"))
    op.drop_table("message_recipients")

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_parent_message_id"))
        batch_op.drop_index(batch_op.f("ix_messages_conversation_id"))
        batch_op.drop_index(batch_op.f("ix_messages_sender_user_id"))
        batch_op.drop_index(batch_op.f("ix_messages_created_at"))
    op.drop_table("messages")


def _seed_permissions() -> None:
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
            "messages.read",
            "Read internal messages",
            "View inbox and sent items.",
        ),
        (
            "messages.send",
            "Send internal messages",
            "Compose and reply to internal messages.",
        ),
        (
            "messages.templates",
            "Manage message templates",
            "Create, update, and delete personal message templates.",
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


def _delete_seeded_permissions() -> None:
    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.Integer()),
        sa.column("code", sa.String(length=100)),
    )

    bind = op.get_bind()
    bind.execute(
        sa.delete(permissions_table).where(
            permissions_table.c.code.in_(
                ["messages.read", "messages.send", "messages.templates"]
            )
        )
    )
