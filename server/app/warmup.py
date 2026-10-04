"""Model warm-up at start-up and the status shown on /health.

The first basal decision after the server starts compiles kernels (~2 s) and whisper-server
is slower on its first request too, so the backend sends one request to each configured
model in the background right after start. Failures are logged; calls still work (rules
only / no transcript) and /health shows the state.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.logging_setup import log_event

logger = logging.getLogger(__name__)


@dataclass
class ModelStatus:
    configured: bool
    warmup: str = "pending"  # pending | ok | failed | skipped
    latency_ms: int | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "warmup": self.warmup,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


@dataclass
class ModelStatuses:
    items: dict[str, ModelStatus] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {name: status.as_dict() for name, status in self.items.items()}


async def _warm_one(name: str, client: Any, status: ModelStatus, limit_seconds: float) -> None:
    try:
        latency = await asyncio.wait_for(client.warm_up(), limit_seconds)
    except Exception as exc:  # noqa: BLE001 - warm-up is best effort
        status.warmup, status.error = "failed", f"{type(exc).__name__}: {str(exc)[:80]}"
        log_event(logger, logging.WARNING, "model_warmup_failed", model=name, error=status.error)
        return
    status.warmup, status.latency_ms = "ok", round(latency)
    log_event(logger, logging.INFO, "model_warmup_ok", model=name, ms=status.latency_ms)


async def warm_up_models(
    clients: dict[str, Any], statuses: ModelStatuses, limit_seconds: float = 30.0
) -> None:
    """Warm up sequentially (both models share one GPU)."""
    for name, client in clients.items():
        status = statuses.items[name]
        if not hasattr(client, "warm_up"):
            status.warmup = "skipped"
            continue
        await _warm_one(name, client, status, limit_seconds)
