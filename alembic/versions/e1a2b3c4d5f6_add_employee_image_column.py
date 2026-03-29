"""add employee image column

Revision ID: e1a2b3c4d5f6
Revises: d8b4e2f1a6c3
Create Date: 2026-03-29 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1a2b3c4d5f6"
down_revision = "d8b4e2f1a6c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.add_column(sa.Column("image", sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_column("image")
