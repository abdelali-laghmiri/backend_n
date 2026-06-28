from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Thread-safe sliding-window rate limiter using per-key timestamp lists."""

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _trim(self, key: str, window: float) -> None:
        cutoff = time.time() - window
        self._buckets[key] = [t for t in self._buckets[key] if t > cutoff]

    def is_allowed(self, key: str, max_requests: int, window_seconds: float) -> bool:
        with self._lock:
            self._trim(key, window_seconds)
            if len(self._buckets[key]) >= max_requests:
                return False
            self._buckets[key].append(time.time())
            return True


_limiter = InMemoryRateLimiter()


def rate_limit(max_requests: int, window_seconds: int = 60):
    """FastAPI dependency factory for per-IP rate limiting."""
    def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "127.0.0.1"
        key = f"{request.url.path}:{client_ip}"
        if not _limiter.is_allowed(key, max_requests, window_seconds):
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_ip": client_ip,
                    "path": request.url.path,
                    "max_requests": max_requests,
                    "window_seconds": window_seconds,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(window_seconds)},
            )
    return dependency
