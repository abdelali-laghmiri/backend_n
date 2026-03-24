from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SetupStatusResponse(BaseModel):
    """Response schema for setup initialization status."""

    initialized: bool
    bootstrap_super_admin_exists: bool
    setup_wizard_required: bool
    detail: str
    initialized_at: datetime | None = None


class BootstrapSuperAdminResponse(BaseModel):
    """Response schema for the bootstrap super admin account."""

    id: int
    matricule: str
    first_name: str
    last_name: str
    email: str
    is_super_admin: bool
    is_active: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SetupInitializeResponse(BaseModel):
    """Response schema for bootstrap super admin creation."""

    initialized: bool
    bootstrap_super_admin_exists: bool
    setup_wizard_required: bool
    detail: str
    super_admin: BootstrapSuperAdminResponse
