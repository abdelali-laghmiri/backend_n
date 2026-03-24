from __future__ import annotations

import os

import uvicorn

from app.core.config import settings


def main() -> None:
    """Run the application with proxy-aware settings for production platforms."""

    port = int(os.getenv("PORT", str(settings.app_port)))
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
    )


if __name__ == "__main__":
    main()
