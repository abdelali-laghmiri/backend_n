"""add employee leave balance days

Revision ID: 9f6c0df7428a
Revises: 5c8eac3602ed
Create Date: 2026-03-23 23:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f6c0df7428a"
down_revision = "5c8eac3602ed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "available_leave_balance_days",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_column("available_leave_balance_days")
