"""seed attendance nfc assign card permission

Revision ID: 8f2c6d1a4b7e
Revises: 7b4c2d1e9f0a
Create Date: 2026-03-29 22:15:00.000000
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8f2c6d1a4b7e"
down_revision = "7b4c2d1e9f0a"
branch_labels = None
depends_on = None


PERMISSION_CODE = "attendance.nfc.assign_card"
PERMISSION_NAME = "Assign NFC cards"
PERMISSION_DESCRIPTION = "Attach NFC cards to employees for attendance identification."
TARGET_JOB_TITLE_CODES = ("RH_MANAGER",)

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


def _get_permission_id(bind) -> int | None:
    """Return the permission id by unique code when it exists."""

    return bind.execute(
        sa.select(permissions_table.c.id)
        .where(permissions_table.c.code == PERMISSION_CODE)
        .limit(1)
    ).scalar_one_or_none()


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    permission_id = _get_permission_id(bind)
    if permission_id is None:
        bind.execute(
            sa.insert(permissions_table).values(
                code=PERMISSION_CODE,
                name=PERMISSION_NAME,
                description=PERMISSION_DESCRIPTION,
                module="attendance",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        permission_id = _get_permission_id(bind)
        if permission_id is None:
            raise RuntimeError(
                f"Failed to load permission '{PERMISSION_CODE}' after insert."
            )
    else:
        bind.execute(
            sa.update(permissions_table)
            .where(permissions_table.c.id == permission_id)
            .values(
                name=PERMISSION_NAME,
                description=PERMISSION_DESCRIPTION,
                module="attendance",
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
    permission_id = _get_permission_id(bind)
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
