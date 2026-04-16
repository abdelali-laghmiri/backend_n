from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.scanner_app.models import AllowedOrigin, ScannerAppBuild
from app.apps.scanner_app.schemas import ScannerAppBuildGenerateRequest
from app.apps.users.models import User
from app.core.config import Settings


class ScannerAppNotFoundError(RuntimeError):
    """Raised when scanner app metadata does not exist."""


class ScannerAppValidationError(RuntimeError):
    """Raised when scanner app metadata is invalid."""


class ScannerAppService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def generate_build(
        self,
        *,
        payload: ScannerAppBuildGenerateRequest,
        current_user: User,
    ) -> ScannerAppBuild:
        if payload.allowed_origin:
            self._upsert_allowed_origin(
                origin=payload.allowed_origin,
                current_user=current_user,
                source="generated",
            )

        self._deactivate_existing_builds()

        build = ScannerAppBuild(
            target_name=payload.target_name,
            backend_base_url=payload.backend_base_url,
            allowed_origin=payload.allowed_origin,
            android_download_url=self.settings.scanner_android_package_url,
            windows_download_url=self.settings.scanner_windows_package_url,
            linux_download_url=self.settings.scanner_linux_package_url,
            generated_by_user_id=current_user.id,
            is_active=True,
        )
        self.db.add(build)
        self.db.commit()
        self.db.refresh(build)
        return build

    def get_active_build(self) -> ScannerAppBuild:
        statement = (
            select(ScannerAppBuild)
            .where(ScannerAppBuild.is_active.is_(True))
            .order_by(ScannerAppBuild.created_at.desc(), ScannerAppBuild.id.desc())
            .limit(1)
        )
        build = self.db.execute(statement).scalar_one_or_none()
        if build is None:
            raise ScannerAppNotFoundError("No scanner app build metadata is available.")
        return build

    def get_download_url(self, *, platform: str, build: ScannerAppBuild) -> str:
        platform_map = {
            "android": build.android_download_url,
            "windows": build.windows_download_url,
            "linux": build.linux_download_url,
        }
        if platform not in platform_map:
            raise ScannerAppValidationError("Unsupported platform.")

        download_url = platform_map[platform]
        if not download_url:
            raise ScannerAppNotFoundError(
                f"No configured download URL is available for platform '{platform}'."
            )
        return download_url

    def list_active_allowed_origins(self) -> list[AllowedOrigin]:
        statement = (
            select(AllowedOrigin)
            .where(AllowedOrigin.is_active.is_(True))
            .order_by(AllowedOrigin.origin.asc())
        )
        return list(self.db.execute(statement).scalars().all())

    def _deactivate_existing_builds(self) -> None:
        statement = select(ScannerAppBuild).where(ScannerAppBuild.is_active.is_(True))
        builds = list(self.db.execute(statement).scalars().all())
        for build in builds:
            build.is_active = False
            self.db.add(build)

    def _upsert_allowed_origin(self, *, origin: str, current_user: User, source: str) -> None:
        statement = select(AllowedOrigin).where(AllowedOrigin.origin == origin).limit(1)
        existing = self.db.execute(statement).scalar_one_or_none()
        if existing is None:
            existing = AllowedOrigin(
                origin=origin,
                source=source,
                is_active=True,
                created_by_user_id=current_user.id,
            )
        else:
            existing.is_active = True
            existing.source = source
            existing.created_by_user_id = current_user.id

        self.db.add(existing)
