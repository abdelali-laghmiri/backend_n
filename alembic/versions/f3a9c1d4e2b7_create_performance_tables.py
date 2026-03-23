"""create performance tables

Revision ID: f3a9c1d4e2b7
Revises: d2c4e6a1b9f0
Create Date: 2026-03-24 00:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f3a9c1d4e2b7"
down_revision = "d2c4e6a1b9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_objectives",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("objective_value", sa.Float(), nullable=False),
        sa.Column("objective_type", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "objective_value > 0",
            name="team_objectives_objective_value_positive",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_team_objectives_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_objectives")),
    )
    with op.batch_alter_table("team_objectives", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_team_objectives_is_active"),
            ["is_active"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_team_objectives_team_id"),
            ["team_id"],
            unique=False,
        )

    op.create_table(
        "team_daily_performances",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("performance_date", sa.Date(), nullable=False),
        sa.Column("objective_value", sa.Float(), nullable=False),
        sa.Column("achieved_value", sa.Float(), nullable=False),
        sa.Column("performance_percentage", sa.Float(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "achieved_value >= 0",
            name="team_daily_performances_achieved_value_non_negative",
        ),
        sa.CheckConstraint(
            "objective_value > 0",
            name="team_daily_performances_objective_value_positive",
        ),
        sa.CheckConstraint(
            "performance_percentage >= 0",
            name="team_daily_performances_performance_percentage_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_team_daily_performances_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_team_daily_performances_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_daily_performances")),
        sa.UniqueConstraint(
            "team_id",
            "performance_date",
            name="uq_team_daily_performances_team_date",
        ),
    )
    with op.batch_alter_table("team_daily_performances", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_team_daily_performances_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_team_daily_performances_performance_date"),
            ["performance_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_team_daily_performances_team_id"),
            ["team_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("team_daily_performances", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_team_daily_performances_team_id"))
        batch_op.drop_index(batch_op.f("ix_team_daily_performances_performance_date"))
        batch_op.drop_index(batch_op.f("ix_team_daily_performances_created_by_user_id"))

    op.drop_table("team_daily_performances")

    with op.batch_alter_table("team_objectives", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_team_objectives_team_id"))
        batch_op.drop_index(batch_op.f("ix_team_objectives_is_active"))

    op.drop_table("team_objectives")
