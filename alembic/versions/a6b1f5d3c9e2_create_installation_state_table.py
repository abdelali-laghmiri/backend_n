"""create installation state table

Revision ID: a6b1f5d3c9e2
Revises: f3a9c1d4e2b7
Create Date: 2026-03-24 10:30:00.000000
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a6b1f5d3c9e2"
down_revision = "f3a9c1d4e2b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "installation_state",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("is_initialized", sa.Boolean(), nullable=False),
        sa.Column("initialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("initialized_by_user_id", sa.Integer(), nullable=True),
        sa.Column("wizard_state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["initialized_by_user_id"],
            ["users.id"],
            name=op.f("fk_installation_state_initialized_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_installation_state")),
    )
    with op.batch_alter_table("installation_state", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_installation_state_initialized_by_user_id"),
            ["initialized_by_user_id"],
            unique=False,
        )

    installation_state = sa.table(
        "installation_state",
        sa.column("id", sa.Integer()),
        sa.column("is_initialized", sa.Boolean()),
        sa.column("initialized_at", sa.DateTime(timezone=True)),
        sa.column("initialized_by_user_id", sa.Integer()),
        sa.column("wizard_state", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        installation_state,
        [
            {
                "id": 1,
                "is_initialized": False,
                "initialized_at": None,
                "initialized_by_user_id": None,
                "wizard_state": {},
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    with op.batch_alter_table("installation_state", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_installation_state_initialized_by_user_id"))

    op.drop_table("installation_state")
