"""create announcements tables

Revision ID: b7c3d9e4f1a2
Revises: 8f2c6d1a4b7e
Create Date: 2026-04-07 00:00:00.000000
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7c3d9e4f1a2"
down_revision = "8f2c6d1a4b7e"
branch_labels = None
depends_on = None


ANNOUNCEMENT_PERMISSIONS = (
    {
        "code": "announcements.read",
        "name": "Read announcements",
        "description": "Read company-wide announcements visible to the current user.",
        "module": "announcements",
        "job_title_codes": ("RH_MANAGER", "DEPARTMENT_MANAGER", "TEAM_LEADER", "EMPLOYEE"),
    },
    {
        "code": "announcements.create",
        "name": "Create announcements",
        "description": "Create company-wide announcements.",
        "module": "announcements",
        "job_title_codes": ("RH_MANAGER", "DEPARTMENT_MANAGER"),
    },
    {
        "code": "announcements.update",
        "name": "Update announcements",
        "description": "Update company-wide announcements and their attachments.",
        "module": "announcements",
        "job_title_codes": ("RH_MANAGER", "DEPARTMENT_MANAGER"),
    },
    {
        "code": "announcements.delete",
        "name": "Delete announcements",
        "description": "Delete company-wide announcements by deactivating them.",
        "module": "announcements",
        "job_title_codes": ("RH_MANAGER", "DEPARTMENT_MANAGER"),
    },
)

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


def _get_permission_id(bind, permission_code: str) -> int | None:
    """Return a permission id by unique code when it exists."""

    return bind.execute(
        sa.select(permissions_table.c.id)
        .where(permissions_table.c.code == permission_code)
        .limit(1)
    ).scalar_one_or_none()


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_announcements_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_announcements_updated_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcements")),
    )
    with op.batch_alter_table("announcements", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_announcements_created_by_user_id"), ["created_by_user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_announcements_expires_at"), ["expires_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_announcements_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_announcements_is_pinned"), ["is_pinned"], unique=False)
        batch_op.create_index(batch_op.f("ix_announcements_published_at"), ["published_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_announcements_type"), ["type"], unique=False)
        batch_op.create_index(batch_op.f("ix_announcements_updated_by_user_id"), ["updated_by_user_id"], unique=False)

    op.create_table(
        "announcement_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("announcement_id", sa.Integer(), nullable=False),
        sa.Column("original_file_name", sa.String(length=255), nullable=False),
        sa.Column("stored_file_name", sa.String(length=255), nullable=False),
        sa.Column("file_url", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=False),
        sa.Column("file_extension", sa.String(length=20), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["announcement_id"],
            ["announcements.id"],
            name=op.f("fk_announcement_attachments_announcement_id_announcements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name=op.f("fk_announcement_attachments_uploaded_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcement_attachments")),
    )
    with op.batch_alter_table("announcement_attachments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_announcement_attachments_announcement_id"), ["announcement_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_announcement_attachments_uploaded_by_user_id"), ["uploaded_by_user_id"], unique=False)

    op.create_table(
        "announcement_reads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("announcement_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["announcement_id"],
            ["announcements.id"],
            name=op.f("fk_announcement_reads_announcement_id_announcements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_announcement_reads_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcement_reads")),
        sa.UniqueConstraint(
            "announcement_id",
            "user_id",
            name="uq_announcement_reads_announcement_user",
        ),
    )
    with op.batch_alter_table("announcement_reads", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_announcement_reads_announcement_id"), ["announcement_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_announcement_reads_user_id"), ["user_id"], unique=False)

    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    for definition in ANNOUNCEMENT_PERMISSIONS:
        permission_id = _get_permission_id(bind, definition["code"])
        if permission_id is None:
            bind.execute(
                sa.insert(permissions_table).values(
                    code=definition["code"],
                    name=definition["name"],
                    description=definition["description"],
                    module=definition["module"],
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            permission_id = _get_permission_id(bind, definition["code"])
            if permission_id is None:
                raise RuntimeError(
                    f"Failed to load permission '{definition['code']}' after insert."
                )
        else:
            bind.execute(
                sa.update(permissions_table)
                .where(permissions_table.c.id == permission_id)
                .values(
                    name=definition["name"],
                    description=definition["description"],
                    module=definition["module"],
                    is_active=True,
                    updated_at=now,
                )
            )

        job_title_rows = bind.execute(
            sa.select(job_titles_table.c.id).where(
                job_titles_table.c.code.in_(definition["job_title_codes"])
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
    permission_ids = [
        permission_id
        for permission_id in (
            _get_permission_id(bind, definition["code"])
            for definition in ANNOUNCEMENT_PERMISSIONS
        )
        if permission_id is not None
    ]
    if permission_ids:
        bind.execute(
            sa.delete(job_title_permissions_table).where(
                job_title_permissions_table.c.permission_id.in_(permission_ids)
            )
        )
        bind.execute(
            sa.delete(permissions_table).where(permissions_table.c.id.in_(permission_ids))
        )

    with op.batch_alter_table("announcement_reads", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_announcement_reads_user_id"))
        batch_op.drop_index(batch_op.f("ix_announcement_reads_announcement_id"))

    op.drop_table("announcement_reads")

    with op.batch_alter_table("announcement_attachments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_announcement_attachments_uploaded_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_announcement_attachments_announcement_id"))

    op.drop_table("announcement_attachments")

    with op.batch_alter_table("announcements", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_announcements_updated_by_user_id"))
        batch_op.drop_index(batch_op.f("ix_announcements_type"))
        batch_op.drop_index(batch_op.f("ix_announcements_published_at"))
        batch_op.drop_index(batch_op.f("ix_announcements_is_pinned"))
        batch_op.drop_index(batch_op.f("ix_announcements_is_active"))
        batch_op.drop_index(batch_op.f("ix_announcements_expires_at"))
        batch_op.drop_index(batch_op.f("ix_announcements_created_by_user_id"))

    op.drop_table("announcements")
