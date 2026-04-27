from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.apps.attendance.models import NfcCard, NfcCardStatusEnum, NfcCardTypeEnum
from app.apps.organization.models import JobTitle
from app.apps.permissions.catalog import CANONICAL_JOB_TITLES, CANONICAL_PERMISSIONS
from app.apps.permissions.models import Permission
from app.apps.setup.service import SetupAlreadyInitializedError, SetupService
from app.core.config import settings
from app.core.database import create_db_engine, create_session_factory
from app.core.database_init import initialize_database_schema

TEMPORARY_CARD_SEED = (
    ("TEMP-001", "TEMP-UID-001"),
    ("TEMP-002", "TEMP-UID-002"),
    ("TEMP-003", "TEMP-UID-003"),
)


def upsert_job_titles(db: Session) -> int:
    created_count = 0
    for definition in CANONICAL_JOB_TITLES:
        existing = db.execute(
            select(JobTitle).where(JobTitle.code == definition["code"]).limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            continue

        db.add(
            JobTitle(
                code=definition["code"],
                name=definition["name"],
                description=definition["description"],
                hierarchical_level=definition["hierarchical_level"],
                is_active=True,
            )
        )
        created_count += 1

    db.commit()
    return created_count


def upsert_permissions(db: Session) -> int:
    created_count = 0
    for definition in CANONICAL_PERMISSIONS:
        existing = db.execute(
            select(Permission).where(Permission.code == definition["code"]).limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            continue

        db.add(
            Permission(
                code=definition["code"],
                name=definition["name"],
                description=definition["description"],
                module=definition["module"],
                is_active=True,
            )
        )
        created_count += 1

    db.commit()
    return created_count


def upsert_temporary_cards(db: Session) -> int:
    created_count = 0
    for label, nfc_uid in TEMPORARY_CARD_SEED:
        existing = db.execute(
            select(NfcCard).where(NfcCard.nfc_uid == nfc_uid).limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            existing.label = label
            existing.card_type = NfcCardTypeEnum.TEMPORARY.value
            existing.status = NfcCardStatusEnum.AVAILABLE.value
            existing.employee_id = None
            existing.is_active = True
            db.add(existing)
            continue

        db.add(
            NfcCard(
                employee_id=None,
                nfc_uid=nfc_uid,
                label=label,
                card_type=NfcCardTypeEnum.TEMPORARY.value,
                status=NfcCardStatusEnum.AVAILABLE.value,
                is_active=True,
            )
        )
        created_count += 1

    db.commit()
    return created_count


def bootstrap_super_admin(db: Session) -> str:
    setup_service = SetupService(db=db, settings=settings)
    try:
        user = setup_service.initialize_system()
        return f"created:{user.matricule}"
    except SetupAlreadyInitializedError:
        user = setup_service.get_super_admin()
        return f"exists:{user.matricule if user else 'unknown'}"
    except IntegrityError:
        db.rollback()
        user = setup_service.get_super_admin()
        return f"exists:{user.matricule if user else 'unknown'}"


def main() -> None:
    initialize_database_schema()
    engine = create_db_engine()
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        admin_status = bootstrap_super_admin(db)
        job_title_count = upsert_job_titles(db)
        permission_count = upsert_permissions(db)
        temporary_card_count = upsert_temporary_cards(db)

    engine.dispose()

    print("Minimal production seed complete.")
    print(f"- super admin: {admin_status}")
    print(f"- job titles created: {job_title_count}")
    print(f"- permissions created: {permission_count}")
    print(f"- temporary cards created: {temporary_card_count}")


if __name__ == "__main__":
    main()
