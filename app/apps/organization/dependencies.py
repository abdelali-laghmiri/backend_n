from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.organization.service import OrganizationService
from app.core.dependencies import get_db_session


def get_organization_service(
    db: Session = Depends(get_db_session),
) -> OrganizationService:
    """Provide the organization service instance."""

    return OrganizationService(db=db)
