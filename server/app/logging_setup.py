"""Structured logging helpers.

Privacy rule: log events carry categories, scores, call ids and error types only. Never pass
transcript text, audio, phone numbers or DTMF digits to `log_event`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

_TOKEN_RE = re.compile(r"((?:device_)?token=)[^&\s\"']+")


def redact_tokens(text: str) -> str:
    return _TOKEN_RE.sub(r"\1***", text)


class RedactTokensFilter(logging.Filter):
    """Masks `token=` / `device_token=` query values (app WebSocket URLs) in log records,
    e.g. uvicorn's access and WebSocket lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and any(isinstance(a, str) and "token=" in a for a in args):
            record.args = tuple(redact_tokens(a) if isinstance(a, str) else a for a in args)
        if isinstance(record.msg, str) and "token=" in record.msg:
            record.msg = redact_tokens(record.msg)
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    redactor = RedactTokensFilter()
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn"):
        target = logging.getLogger(name)
        if not any(isinstance(f, RedactTokensFilter) for f in target.filters):
            target.addFilter(redactor)


def log_event(logger: logging.Logger, level: int, event: str, /, **fields: Any) -> None:
    """Log `event` followed by its fields as one JSON object (easy to grep and parse)."""
    if not logger.isEnabledFor(level):
        return
    payload = json.dumps(fields, default=str, ensure_ascii=False, sort_keys=True)
    logger.log(level, "%s %s", event, payload)
