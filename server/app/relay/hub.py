"""AppHub: control-channel connections, active call bridges and one-time call tokens."""

from __future__ import annotations

import hmac
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.calls.sender import SafeSender
from app.logging_setup import log_event
from app.relay import protocol

if TYPE_CHECKING:
    from app.calls.bridge import CallBridge

logger = logging.getLogger(__name__)


@dataclass
class _CallToken:
    token: str
    expires_at: float


class AppHub:
    def __init__(self, device_token: str, clock: Callable[[], float] = time.monotonic) -> None:
        self._device_token = device_token
        self._clock = clock
        self._controls: set[SafeSender] = set()
        self._tokens: dict[str, _CallToken] = {}
        self.bridges: dict[str, CallBridge] = {}

    # ------------------------------------------------------------------ control channel
    @property
    def device_token_configured(self) -> bool:
        return bool(self._device_token)

    def check_device_token(self, token: str) -> bool:
        if not self._device_token or not token:
            return False
        return hmac.compare_digest(token.encode(), self._device_token.encode())

    @property
    def online(self) -> bool:
        """True while at least one senior app control channel is open."""
        return any(not c.closed for c in self._controls)

    @property
    def control_count(self) -> int:
        return sum(1 for c in self._controls if not c.closed)

    def add_control(self, sender: SafeSender) -> None:
        self._controls.add(sender)

    def remove_control(self, sender: SafeSender) -> None:
        self._controls.discard(sender)

    async def broadcast(self, message: dict[str, object]) -> int:
        delivered = 0
        for sender in list(self._controls):
            if await sender.send_json(message):
                delivered += 1
        return delivered

    async def shutdown(self) -> None:
        await self.broadcast(protocol.protection_status(False))
        for sender in list(self._controls):
            await sender.close(protocol.CLOSE_NORMAL)
        self._controls.clear()

    # ------------------------------------------------------------------ calls
    def register(self, bridge: CallBridge) -> str:
        """Track a bridge and issue its one-time call-channel token."""
        self._purge()
        self.bridges[bridge.call_id] = bridge
        token = secrets.token_urlsafe(24)
        self._tokens[bridge.call_id] = _CallToken(
            token, self._clock() + protocol.CALL_TOKEN_TTL_SECONDS
        )
        return token

    def unregister(self, call_id: str) -> None:
        self.bridges.pop(call_id, None)
        self._tokens.pop(call_id, None)

    def consume_token(self, call_id: str, token: str) -> CallBridge | None:
        """Single use: a valid token is deleted on first use."""
        self._purge()
        entry = self._tokens.get(call_id)
        if entry is None or not token:
            return None
        if not hmac.compare_digest(entry.token.encode(), token.encode()):
            return None
        del self._tokens[call_id]
        return self.bridges.get(call_id)

    def _purge(self) -> None:
        now = self._clock()
        expired = [cid for cid, t in self._tokens.items() if t.expires_at <= now]
        for cid in expired:
            del self._tokens[cid]
            log_event(logger, logging.INFO, "app_call_token_expired", call_id=cid)
