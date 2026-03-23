from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.employees.service import EmployeesService
from app.core.dependencies import get_db_session


def get_employees_service(
    db: Session = Depends(get_db_session),
) -> EmployeesService:
    """Provide the employees service instance."""

    return EmployeesService(db=db)
