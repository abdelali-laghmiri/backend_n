"""create attendance tables

Revision ID: d2c4e6a1b9f0
Revises: 9f6c0df7428a
Create Date: 2026-03-24 00:05:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d2c4e6a1b9f0"
down_revision = "9f6c0df7428a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance_raw_scan_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("reader_type", sa.String(length=10), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_attendance_raw_scan_events_employee_id_employees"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_attendance_raw_scan_events_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance_raw_scan_events")),
    )
    with op.batch_alter_table("attendance_raw_scan_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_attendance_raw_scan_events_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_attendance_raw_scan_events_employee_id"),
            ["employee_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_attendance_raw_scan_events_reader_type"),
            ["reader_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_attendance_raw_scan_events_scanned_at"),
            ["scanned_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_attendance_raw_scan_events_user_id"),
            ["user_id"],
            unique=False,
        )

    op.create_table(
        "attendance_daily_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("first_check_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worked_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("linked_request_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_attendance_daily_summaries_employee_id_employees"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["linked_request_id"],
            ["requests.id"],
            name=op.f("fk_attendance_daily_summaries_linked_request_id_requests"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance_daily_summaries")),
        sa.UniqueConstraint(
            "employee_id",
            "attendance_date",
            name="uq_attendance_daily_summaries_employee_date",
        ),
    )
    with op.batch_alter_table("attendance_daily_summaries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_attendance_daily_summaries_attendance_date"),
            ["attendance_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_attendance_daily_summaries_employee_id"),
            ["employee_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_attendance_daily_summaries_linked_request_id"),
            ["linked_request_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_attendance_daily_summaries_status"),
            ["status"],
            unique=False,
        )

    op.create_table(
        "attendance_monthly_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("report_year", sa.Integer(), nullable=False),
        sa.Column("report_month", sa.Integer(), nullable=False),
        sa.Column("total_worked_days", sa.Integer(), nullable=False),
        sa.Column("total_worked_minutes", sa.Integer(), nullable=False),
        sa.Column("total_present_days", sa.Integer(), nullable=False),
        sa.Column("total_absence_days", sa.Integer(), nullable=False),
        sa.Column("total_leave_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_attendance_monthly_reports_employee_id_employees"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance_monthly_reports")),
        sa.UniqueConstraint(
            "employee_id",
            "report_year",
            "report_month",
            name="uq_attendance_monthly_reports_employee_period",
        ),
    )
    with op.batch_alter_table("attendance_monthly_reports", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_attendance_monthly_reports_employee_id"),
            ["employee_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_attendance_monthly_reports_report_month"),
            ["report_month"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_attendance_monthly_reports_report_year"),
            ["report_year"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("attendance_monthly_reports", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_attendance_monthly_reports_report_year"))
        batch_op.drop_index(batch_op.f("ix_attendance_monthly_reports_report_month"))
        batch_op.drop_index(batch_op.f("ix_attendance_monthly_reports_employee_id"))

    op.drop_table("attendance_monthly_reports")

    with op.batch_alter_table("attendance_daily_summaries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_attendance_daily_summaries_status"))
        batch_op.drop_index(batch_op.f("ix_attendance_daily_summaries_linked_request_id"))
        batch_op.drop_index(batch_op.f("ix_attendance_daily_summaries_employee_id"))
        batch_op.drop_index(batch_op.f("ix_attendance_daily_summaries_attendance_date"))

    op.drop_table("attendance_daily_summaries")

    with op.batch_alter_table("attendance_raw_scan_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_attendance_raw_scan_events_user_id"))
        batch_op.drop_index(batch_op.f("ix_attendance_raw_scan_events_scanned_at"))
        batch_op.drop_index(batch_op.f("ix_attendance_raw_scan_events_reader_type"))
        batch_op.drop_index(batch_op.f("ix_attendance_raw_scan_events_employee_id"))
        batch_op.drop_index(batch_op.f("ix_attendance_raw_scan_events_created_at"))

    op.drop_table("attendance_raw_scan_events")
