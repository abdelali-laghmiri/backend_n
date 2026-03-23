from __future__ import annotations

from app.apps.employees.models import Employee  # noqa: F401
from app.apps.organization.models import Department, JobTitle, Team  # noqa: F401
from app.apps.permissions.models import JobTitlePermissionAssignment, Permission  # noqa: F401
from app.apps.requests.models import (  # noqa: F401
    RequestActionHistory,
    RequestFieldValue,
    RequestType,
    RequestTypeField,
    RequestWorkflowStep,
    WorkflowRequest,
)
from app.apps.users.models import User  # noqa: F401
from app.core.database import Base

# Import model modules here so Alembic can discover SQLAlchemy metadata.

__all__ = ["Base"]
