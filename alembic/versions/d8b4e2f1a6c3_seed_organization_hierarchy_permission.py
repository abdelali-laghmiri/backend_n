"""seed organization hierarchy permission

Revision ID: d8b4e2f1a6c3
Revises: c4b7e1a2d9f0
Create Date: 2026-03-29 00:00:00.000000
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d8b4e2f1a6c3"
down_revision = "c4b7e1a2d9f0"
branch_labels = None
depends_on = None


PERMISSION_CODE = "organization.read_hierarchy"
PERMISSION_NAME = "Read organization hierarchy"
PERMISSION_DESCRIPTION = (
    "View hierarchy trees for the current user and the full company organigram."
)
TARGET_JOB_TITLE_CODES = ("RH_MANAGER", "DEPARTMENT_MANAGER", "TEAM_LEADER")

permissions_table = sa.table(
    "permissions",
    sa.column("id", sa.Integer()),
    sa.column("code", sa.String(length=100)),
    sa.column("name", sa.String(length=120)),
    sa.column("description", sa.Text()),
    sa.column("module", sa.String(length=50)),
    sa.column("is_active", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)

job_titles_table = sa.table(
    "job_titles",
    sa.column("id", sa.Integer()),
    sa.column("code", sa.String(length=50)),
)

job_title_permissions_table = sa.table(
    "job_title_permissions",
    sa.column("id", sa.Integer()),
    sa.column("job_title_id", sa.Integer()),
    sa.column("permission_id", sa.Integer()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    permission_row = (
        bind.execute(
            sa.select(
                permissions_table.c.id,
            )
            .where(permissions_table.c.code == PERMISSION_CODE)
            .limit(1)
        )
        .mappings()
        .first()
    )

    if permission_row is None:
        result = bind.execute(
            sa.insert(permissions_table).values(
                code=PERMISSION_CODE,
                name=PERMISSION_NAME,
                description=PERMISSION_DESCRIPTION,
                module="organization",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        permission_id = result.inserted_primary_key[0]
    else:
        permission_id = permission_row["id"]
        bind.execute(
            sa.update(permissions_table)
            .where(permissions_table.c.id == permission_id)
            .values(
                name=PERMISSION_NAME,
                description=PERMISSION_DESCRIPTION,
                module="organization",
                is_active=True,
                updated_at=now,
            )
        )

    job_title_rows = bind.execute(
        sa.select(job_titles_table.c.id).where(
            job_titles_table.c.code.in_(TARGET_JOB_TITLE_CODES)
        )
    ).all()

    for job_title_id, in job_title_rows:
        existing_assignment = bind.execute(
            sa.select(job_title_permissions_table.c.id)
            .where(
                job_title_permissions_table.c.job_title_id == job_title_id,
                job_title_permissions_table.c.permission_id == permission_id,
            )
            .limit(1)
        ).first()
        if existing_assignment is not None:
            continue

        bind.execute(
            sa.insert(job_title_permissions_table).values(
                job_title_id=job_title_id,
                permission_id=permission_id,
                created_at=now,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    permission_id = bind.execute(
        sa.select(permissions_table.c.id)
        .where(permissions_table.c.code == PERMISSION_CODE)
        .limit(1)
    ).scalar_one_or_none()
    if permission_id is None:
        return

    bind.execute(
        sa.delete(job_title_permissions_table).where(
            job_title_permissions_table.c.permission_id == permission_id
        )
    )
    bind.execute(
        sa.delete(permissions_table).where(permissions_table.c.id == permission_id)
    )
