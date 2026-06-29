from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.apps.tasks.service import TasksService
from app.core.dependencies import get_db_session


def get_tasks_service(
    db: Session = Depends(get_db_session),
) -> TasksService:
    """Provide the tasks service instance."""

    return TasksService(db=db)
