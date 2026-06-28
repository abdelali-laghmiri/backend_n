from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

import logging

from app.core.ctx import request_id_var

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request and response."""

    def __init__(self, app: ASGIApp, *, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request_id_var.set(request_id)

        start = time.monotonic()
        method = request.method
        path = request.url.path

        logger.info(
            "Request started",
            extra={"request_id": request_id, "method": method, "path": path},
        )

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled exception processing request",
                extra={"request_id": request_id, "method": method, "path": path},
            )
            raise

        elapsed_ms = int((time.monotonic() - start) * 1000)
        response.headers[self._header_name] = request_id

        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": elapsed_ms,
            },
        )

        return response
