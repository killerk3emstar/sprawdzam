"""Structured logging helpers.

Privacy rule: log events carry categories, scores, call ids and error types only. Never pass
transcript text, audio, phone numbers or DTMF digits to `log_event`.
"""

from __future__ import annotations

import json
import logging
from typing import Any


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def log_event(logger: logging.Logger, level: int, event: str, /, **fields: Any) -> None:
    """Log `event` followed by its fields as one JSON object (easy to grep and parse)."""
    if not logger.isEnabledFor(level):
        return
    payload = json.dumps(fields, default=str, ensure_ascii=False, sort_keys=True)
    logger.log(level, "%s %s", event, payload)
