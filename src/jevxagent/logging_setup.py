"""Structured logging.

JSON-lines logging that never writes secrets: any value under a key matching
api_key/authorization/token/password/secret is redacted.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from .config import is_sensitive_key

LOGGER_NAME = "jevxagent"


def _redact_object(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            str(k): ("***redacted***" if is_sensitive_key(str(k)) else _redact_object(v))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [_redact_object(v) for v in obj]
    return obj


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
        }
        if record.getMessage():
            payload["event"] = record.getMessage()
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(_redact_object(extra))
        if record.exc_info and record.exc_info[0] is not None:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(event, extra={"extra_fields": fields})
