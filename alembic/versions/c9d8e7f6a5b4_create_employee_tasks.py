"""create employee tasks

Revision ID: c9d8e7f6a5b4
Revises: 7a8b9c0d1e2f
Create Date: 2026-06-29
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TASK_PERMISSION_DEFINITIONS = (
    (
        "tasks.view",
        "View my tasks",
        "View tasks assigned to the current employee.",
    ),
    (
        "tasks.complete",
        "Complete my tasks",
        "Mark assigned tasks as completed.",
    ),
    (
        "tasks.manage",
        "Manage tasks",
        "Assign and list employee tasks.",
    ),
)

TASK_JOB_TITLE_ASSIGNMENTS = {
    "tasks.view": (
        "SUPER_ADMIN",
        "RH_MANAGER",
        "OPERATIONS_MANAGER",
        "DEPARTMENT_MANAGER",
        "FINANCE_PAYROLL",
        "ATTENDANCE_MANAGER",
        "HR_ASSISTANT",
        "TEAM_LEADER",
        "IT_SUPPORT",
        "EMPLOYEE",
    ),
    "tasks.complete": (
        "SUPER_ADMIN",
        "RH_MANAGER",
        "OPERATIONS_MANAGER",
        "DEPARTMENT_MANAGER",
        "FINANCE_PAYROLL",
        "ATTENDANCE_MANAGER",
        "HR_ASSISTANT",
        "TEAM_LEADER",
        "IT_SUPPORT",
        "EMPLOYEE",
    ),
    "tasks.manage": (
        "SUPER_ADMIN",
        "RH_MANAGER",
        "OPERATIONS_MANAGER",
        "DEPARTMENT_MANAGER",
        "FINANCE_PAYROLL",
        "ATTENDANCE_MANAGER",
        "HR_ASSISTANT",
        "TEAM_LEADER",
        "IT_SUPPORT",
    ),
}

permissions_table = sa.table(
    "permissions",
    sa.column("id", sa.Integer()),
    sa.column("code", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.String()),
    sa.column("module", sa.String()),
    sa.column("is_active", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)

job_titles_table = sa.table(
    "job_titles",
    sa.column("id", sa.Integer()),
    sa.column("code", sa.String()),
)

job_title_permissions_table = sa.table(
    "job_title_permissions",
    sa.column("id", sa.Integer()),
    sa.column("job_title_id", sa.Integer()),
    sa.column("permission_id", sa.Integer()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.create_table(
        "employee_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_employee_tasks_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_employee_tasks_employee_id_employees"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employee_tasks")),
    )
    with op.batch_alter_table("employee_tasks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_employee_tasks_completed_at"),
            ["completed_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_employee_tasks_created_by_user_id"),
            ["created_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_employee_tasks_due_date"),
            ["due_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_employee_tasks_employee_id"),
            ["employee_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_employee_tasks_priority"),
            ["priority"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_employee_tasks_status"),
            ["status"],
            unique=False,
        )

    _seed_task_permissions()


def downgrade() -> None:
    _delete_task_permissions()

    with op.batch_alter_table("employee_tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_employee_tasks_status"))
        batch_op.drop_index(batch_op.f("ix_employee_tasks_priority"))
        batch_op.drop_index(batch_op.f("ix_employee_tasks_employee_id"))
        batch_op.drop_index(batch_op.f("ix_employee_tasks_due_date"))
        batch_op.drop_index(batch_op.f("ix_employee_tasks_created_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_employee_tasks_completed_at"))

    op.drop_table("employee_tasks")


def _get_permission_id(bind, permission_code: str) -> int | None:
    return bind.execute(
        sa.select(permissions_table.c.id)
        .where(permissions_table.c.code == permission_code)
        .limit(1)
    ).scalar_one_or_none()


def _seed_task_permissions() -> None:
    bind = op.get_bind()
    now = sa.func.now()

    for code, name, description in TASK_PERMISSION_DEFINITIONS:
        permission_id = _get_permission_id(bind, code)
        if permission_id is None:
            bind.execute(
                sa.insert(permissions_table).values(
                    code=code,
                    name=name,
                    description=description,
                    module="tasks",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            permission_id = _get_permission_id(bind, code)
        else:
            bind.execute(
                sa.update(permissions_table)
                .where(permissions_table.c.id == permission_id)
                .values(
                    name=name,
                    description=description,
                    module="tasks",
                    is_active=True,
                    updated_at=now,
                )
            )

        if permission_id is None:
            continue

        job_title_codes = TASK_JOB_TITLE_ASSIGNMENTS.get(code, ())
        job_title_ids = bind.execute(
            sa.select(job_titles_table.c.id).where(
                job_titles_table.c.code.in_(job_title_codes)
            )
        ).scalars().all()
        for job_title_id in job_title_ids:
            existing_assignment_id = bind.execute(
                sa.select(job_title_permissions_table.c.id)
                .where(
                    job_title_permissions_table.c.job_title_id == job_title_id,
                    job_title_permissions_table.c.permission_id == permission_id,
                )
                .limit(1)
            ).scalar_one_or_none()
            if existing_assignment_id is None:
                bind.execute(
                    sa.insert(job_title_permissions_table).values(
                        job_title_id=job_title_id,
                        permission_id=permission_id,
                        created_at=now,
                    )
                )


def _delete_task_permissions() -> None:
    bind = op.get_bind()
    permission_ids = [
        permission_id
        for permission_id in (
            _get_permission_id(bind, code)
            for code, _name, _description in TASK_PERMISSION_DEFINITIONS
        )
        if permission_id is not None
    ]
    if not permission_ids:
        return

    bind.execute(
        sa.delete(job_title_permissions_table).where(
            job_title_permissions_table.c.permission_id.in_(permission_ids)
        )
    )
    bind.execute(
        sa.delete(permissions_table).where(permissions_table.c.id.in_(permission_ids))
    )
