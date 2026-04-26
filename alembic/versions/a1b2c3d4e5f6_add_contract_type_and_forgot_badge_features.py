"""add_contract_type_and_forgot_badge_features

Revision ID: a1b2c3d4e5f6
Revises: 4c2f7a9b1d0e
Create Date: 2026-04-26

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "4c2f7a9b1d0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("contract_type", sa.String(20), nullable=False, server_default="INTERNAL"),
    )
    op.add_column("employees", sa.Column("external_company_name", sa.String(255), nullable=True))
    op.create_index("ix_employees_contract_type", "employees", ["contract_type"])

    op.create_table(
        "forgot_badge_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_by_user_id", sa.Integer(), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nfc_card_id", sa.Integer(), nullable=True),
        sa.Column("valid_for_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["handled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["nfc_card_id"], ["nfc_cards.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forgot_badge_requests_employee_id", "forgot_badge_requests", ["employee_id"])
    op.create_index("ix_forgot_badge_requests_status", "forgot_badge_requests", ["status"])
    op.create_index("ix_forgot_badge_requests_valid_for_date", "forgot_badge_requests", ["valid_for_date"])

    op.create_table(
        "temporary_nfc_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("nfc_card_id", sa.Integer(), nullable=False),
        sa.Column("forgot_badge_request_id", sa.Integer(), nullable=True),
        sa.Column("assigned_by_user_id", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_for_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("check_in_attendance_id", sa.Integer(), nullable=True),
        sa.Column("check_out_attendance_id", sa.Integer(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["nfc_card_id"], ["nfc_cards.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["forgot_badge_request_id"], ["forgot_badge_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["check_in_attendance_id"], ["attendance_raw_scan_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["check_out_attendance_id"], ["attendance_raw_scan_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_temporary_nfc_assignments_employee_id", "temporary_nfc_assignments", ["employee_id"])
    op.create_index("ix_temporary_nfc_assignments_nfc_card_id", "temporary_nfc_assignments", ["nfc_card_id"])
    op.create_index("ix_temporary_nfc_assignments_status", "temporary_nfc_assignments", ["status"])
    op.create_index("ix_temporary_nfc_assignments_valid_for_date", "temporary_nfc_assignments", ["valid_for_date"])


def downgrade() -> None:
    op.drop_table("temporary_nfc_assignments")
    op.drop_table("forgot_badge_requests")
    op.drop_index("ix_employees_contract_type")
    op.drop_column("employees", "external_company_name")
    op.drop_column("employees", "contract_type")