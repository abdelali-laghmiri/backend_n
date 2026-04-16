from __future__ import annotations

from sqlalchemy import select

from app.apps.scanner_app.models import AllowedOrigin
from app.core.config import Settings
from app.core.database import create_session_factory, engine


def get_merged_browser_origins(settings: Settings) -> list[str]:
    """Merge trusted env origins with active DB-managed origins."""

    merged: list[str] = []
    seen: set[str] = set()

    def add_origin(raw_origin: str) -> None:
        normalized = raw_origin.strip().rstrip("/").lower()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        merged.append(normalized)

    for env_origin in settings.cors_allow_origins:
        add_origin(env_origin)

    # Startup must remain resilient before migrations create allowed_origins.
    session_factory = create_session_factory(engine)
    with session_factory() as db:
        try:
            statement = (
                select(AllowedOrigin.origin)
                .where(AllowedOrigin.is_active.is_(True))
                .order_by(AllowedOrigin.origin.asc())
            )
            rows = db.execute(statement).scalars().all()
            for origin in rows:
                add_origin(origin)
        except Exception:
            return merged

    return merged
