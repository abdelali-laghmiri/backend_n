"""add resolver job title to request workflow steps

Revision ID: 4c2f7a9b1d0e
Revises: 3f7a2d1c9e0b
Create Date: 2026-04-20 14:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "4c2f7a9b1d0e"
down_revision = "3f7a2d1c9e0b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("request_workflow_steps", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resolver_job_title_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_request_workflow_steps_resolver_job_title_id"),
            ["resolver_job_title_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            batch_op.f(
                "fk_request_workflow_steps_resolver_job_title_id_job_titles"
            ),
            "job_titles",
            ["resolver_job_title_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("request_workflow_steps", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_request_workflow_steps_resolver_job_title_id_job_titles"),
            type_="foreignkey",
        )
        batch_op.drop_index(batch_op.f("ix_request_workflow_steps_resolver_job_title_id"))
        batch_op.drop_column("resolver_job_title_id")
