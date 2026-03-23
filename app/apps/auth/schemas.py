from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuthenticatedUserResponse(BaseModel):
    """Response schema for the authenticated account identity."""

    id: int
    matricule: str
    first_name: str
    last_name: str
    email: str
    is_super_admin: bool
    is_active: bool
    must_change_password: bool
    has_full_access: bool
    permissions: list[str]

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    """Request schema for user login."""

    matricule: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=255)


class LoginResponse(BaseModel):
    """Response schema for a successful login."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: AuthenticatedUserResponse


class ChangePasswordRequest(BaseModel):
    """Request schema for an authenticated password change."""

    current_password: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)

    @model_validator(mode="after")
    def validate_new_password(self) -> "ChangePasswordRequest":
        """Prevent reusing the current password as the new password."""

        if self.current_password == self.new_password:
            raise ValueError("The new password must be different from the current password.")

        return self


class ChangePasswordResponse(BaseModel):
    """Response schema for a successful password change."""

    detail: str
    user: AuthenticatedUserResponse
