"""Structured logging with a redaction filter applied to every record."""

from __future__ import annotations

import logging

from .security import redact_text


class RedactionFilter(logging.Filter):
    """Scrub the rendered message of any sensitive-looking content.

    Applied to all handlers so a stray ``logger.info(user_input)`` can never
    leak a token, email or signed URL into the logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once, with the redaction filter attached."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Uvicorn's own loggers should inherit the same redaction filter.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False
