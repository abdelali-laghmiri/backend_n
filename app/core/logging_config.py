from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from typing import Any

from app.core.ctx import request_id_var

SENSITIVE_FIELD_NAMES = frozenset({
    "password",
    "token",
    "secret",
    "authorization",
    "access_token",
    "refresh_token",
    "jwt",
    "credential",
    "api_key",
    "api-key",
    "secret_key",
    "secret-key",
    "database_url",
    "connection_string",
    "dsn",
})

SENSITIVE_TEXT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "[JWT_REDACTED]"),
    (re.compile(r"(://)([^:/\s]+):([^@\s]+)@"), r"\1[REDACTED]:[REDACTED]@"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_-]+\.[A-Za-z0-9_-]"), "Bearer [REDACTED]"),
    (re.compile(r"\bpassword\s*[=:]\s*\S+", re.IGNORECASE), "password=[REDACTED]"),
    (re.compile(r"\bSECRET_KEY\s*=\s*\S+"), "SECRET_KEY=[REDACTED]"),
    (re.compile(r"\bDATABASE_URL\s*=\s*\S+"), "DATABASE_URL=[REDACTED]"),
]


class SensitiveDataFilter(logging.Filter):
    """Redact sensitive fields from log record args and extra data."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if args:
            cleaned = tuple(
                self._sanitize(arg) for arg in (args if isinstance(args, tuple) else (args,))
            )
            record.args = cleaned
        return True

    @classmethod
    def _sanitize(cls, value: object) -> object:
        if isinstance(value, Mapping):
            return {k: cls._sanitize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return type(value)(cls._sanitize(v) for v in value)
        if isinstance(value, str) and any(
            sensitive in value.lower() for sensitive in SENSITIVE_FIELD_NAMES
        ):
            return cls._redact(value)
        return value

    @staticmethod
    def _redact(value: str) -> str:
        if len(value) > 80:
            return value[:8] + "...[REDACTED]"
        return "[REDACTED]"


class JsonFormatter(logging.Formatter):
    """Output log records as newline-delimited JSON with redaction."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", None) or request_id_var.get()

        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact_text(record.getMessage()),
        }
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info and record.exc_info[0]:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)

    def formatException(self, exc_info) -> str:
        text = super().formatException(exc_info)
        return self._redact_text(text)

    @staticmethod
    def _redact_text(text: str) -> str:
        for pattern, replacement in SENSITIVE_TEXT_PATTERNS:
            text = pattern.sub(replacement, text)
        return text


def setup_logging(*, level: str = "INFO", fmt: str = "json") -> None:
    """Configure the root logger for structured production logging."""

    raw_level = level.strip().upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(raw_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if fmt.strip().lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    handler.addFilter(SensitiveDataFilter())
    root_logger.addHandler(handler)

    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers.clear()
    uvicorn_logger.propagate = True
