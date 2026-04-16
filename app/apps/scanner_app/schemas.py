from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def normalize_required(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("This field cannot be blank.")
    return normalized


class ScannerAppBuildGenerateRequest(BaseModel):
    target_name: str = Field(min_length=1, max_length=120)
    backend_base_url: str = Field(min_length=1, max_length=255)
    allowed_origin: str | None = Field(default=None, max_length=255)

    @field_validator("target_name")
    @classmethod
    def validate_target_name(cls, value: str) -> str:
        return normalize_required(value)

    @field_validator("backend_base_url")
    @classmethod
    def validate_backend_base_url(cls, value: str) -> str:
        normalized = normalize_required(value)
        if not (normalized.startswith("https://") or normalized.startswith("http://")):
            raise ValueError("backend_base_url must start with http:// or https://")
        return normalized.rstrip("/")

    @field_validator("allowed_origin")
    @classmethod
    def validate_allowed_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip().rstrip("/")
        if not normalized:
            return None
        if not (normalized.startswith("https://") or normalized.startswith("http://")):
            raise ValueError("allowed_origin must start with http:// or https://")
        return normalized


class ScannerAppBuildResponse(BaseModel):
    id: int
    target_name: str
    backend_base_url: str
    allowed_origin: str | None
    android_download_url: str | None
    windows_download_url: str | None
    linux_download_url: str | None
    generated_by_user_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ScannerAppDownloadQueryResponse(BaseModel):
    platform: Literal["android", "windows", "linux"]
    download_url: str


class AllowedOriginResponse(BaseModel):
    id: int
    origin: str
    source: str
    is_active: bool
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
