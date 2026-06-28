"""add employee gender column

Revision ID: 7a8b9c0d1e2f
Revises: b6d4e8f0c2a1
Create Date: 2026-05-09 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7a8b9c0d1e2f"
down_revision = "b6d4e8f0c2a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.add_column(sa.Column("gender", sa.String(length=10), nullable=True, index=True))


def downgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_column("gender")
