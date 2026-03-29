"""create nfc cards table

Revision ID: 7b4c2d1e9f0a
Revises: e1a2b3c4d5f6
Create Date: 2026-03-29 20:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7b4c2d1e9f0a"
down_revision = "e1a2b3c4d5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nfc_cards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("nfc_uid", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_nfc_cards_employee_id_employees"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nfc_cards")),
    )
    with op.batch_alter_table("nfc_cards", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_nfc_cards_employee_id"),
            ["employee_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_nfc_cards_nfc_uid"),
            ["nfc_uid"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("nfc_cards", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_nfc_cards_nfc_uid"))
        batch_op.drop_index(batch_op.f("ix_nfc_cards_employee_id"))

    op.drop_table("nfc_cards")
