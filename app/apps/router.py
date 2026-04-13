from __future__ import annotations

from fastapi import APIRouter

from app.apps.announcements.router import router as announcements_router
from app.apps.attendance.router import router as attendance_router
from app.apps.auth.router import router as auth_router
from app.apps.messages.router import router as messages_router
from app.apps.dashboard.router import router as dashboard_router
from app.apps.employees.router import router as employees_router
from app.apps.notifications.router import router as notifications_router
from app.apps.organization.router import router as organization_router
from app.apps.permissions.router import router as permissions_router
from app.apps.performance.router import router as performance_router
from app.apps.requests.router import router as requests_router
from app.apps.setup.router import router as setup_router
from app.apps.users.router import router as users_router

api_router = APIRouter()

api_router.include_router(setup_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(organization_router)
api_router.include_router(employees_router)
api_router.include_router(notifications_router)
api_router.include_router(messages_router)
api_router.include_router(announcements_router)
api_router.include_router(permissions_router)
api_router.include_router(requests_router)
api_router.include_router(attendance_router)
api_router.include_router(performance_router)
api_router.include_router(dashboard_router)
