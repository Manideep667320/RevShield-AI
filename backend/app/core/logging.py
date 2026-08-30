"""
Centralized structured logging factory.
All modules call get_logger(__name__) — no per-file setup.
"""
import logging
import sys
from typing import Any
from app.core.config import settings


class JSONFormatter(logging.Formatter):
    """Formats log records as structured key=value for easy parsing."""

    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            fields["exception"] = self.formatException(record.exc_info)
        return " | ".join(f"{k}={v}" for k, v in fields.items())


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False
    return logger
