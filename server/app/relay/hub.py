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
from app.config import Lang
from app.logging_setup import log_event
from app.relay import protocol
from app.relay.device import DeviceSettings

if TYPE_CHECKING:
    from app.calls.bridge import CallBridge
    from app.events import EventBus

logger = logging.getLogger(__name__)


TRUSTED_ALERT_TTL_SECONDS = 120.0  # an undelivered alert waits this long for the app
_ALERT_MEMORY_SECONDS = 3600.0  # call ids remembered for the one-alert-per-call guard
_ALERT_ERRORS = {"no_permission", "no_number", "send_failed"}


@dataclass
class _PendingAlert:
    message: dict[str, object]
    queued_at: float


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
        # v0: one senior device per backend; the last settings message wins.
        self.device_settings: DeviceSettings | None = None
        self.events: EventBus | None = None
        # Trusted-person alerts: at most one per call id, ever (also across reconnects).
        self._alerted: dict[str, float] = {}  # call id -> first time an alert was requested
        self._pending_alerts: dict[str, _PendingAlert] = {}
        self._alert_results: set[str] = set()

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

    # ------------------------------------------------------------------ trusted-person alert
    async def send_trusted_alert(self, call_id: str, message: dict[str, object]) -> bool:
        """Ask the senior's phone to text the trusted person (`alert_trusted`). At most once
        per call id; when no app is connected the alert waits up to TRUSTED_ALERT_TTL_SECONDS
        for a control connection. Returns True if delivered now."""
        self._purge_alerts()
        if call_id in self._alerted:
            log_event(logger, logging.WARNING, "trusted_alert_duplicate", call_id=call_id)
            return False
        self._alerted[call_id] = self._clock()
        delivered = await self.broadcast(message) if self.online else 0
        if delivered:
            self._alert_delivered(call_id, delivered)
            return True
        self._pending_alerts[call_id] = _PendingAlert(message, self._clock())
        log_event(logger, logging.INFO, "trusted_alert_queued", call_id=call_id)
        return False

    async def deliver_pending_alerts(self, sender: SafeSender) -> int:
        """Called when a control channel opens: deliver queued, unexpired alerts once."""
        self._purge_alerts()
        sent = 0
        for call_id in list(self._pending_alerts):
            pending = self._pending_alerts.pop(call_id, None)
            if pending is None:
                continue
            if await sender.send_json(pending.message):
                self._alert_delivered(call_id, 1)
                sent += 1
            else:
                self._pending_alerts[call_id] = pending
        return sent

    def _alert_delivered(self, call_id: str, connections: int) -> None:
        log_event(
            logger, logging.INFO, "trusted_alert_sent", call_id=call_id, connections=connections
        )
        if self.events is not None:
            self.events.action(call_id, "sms_requested", "alert_trusted sent to the senior's phone")

    def on_alert_result(self, call_id: str, sent: bool, error: str | None) -> None:
        """`alert_trusted_result` from the app; the first result per alerted call counts."""
        if call_id not in self._alerted or call_id in self._pending_alerts:
            log_event(logger, logging.WARNING, "trusted_alert_result_unknown", call_id=call_id)
            return
        if call_id in self._alert_results:
            return
        self._alert_results.add(call_id)
        reason = None if sent else (error if error in _ALERT_ERRORS else "send_failed")
        log_event(
            logger,
            logging.INFO if sent else logging.WARNING,
            "trusted_alert_result",
            call_id=call_id,
            sent=sent,
            error=reason,
        )
        if self.events is not None:
            if sent:
                self.events.action(call_id, "sms_sent", "SMS sent by the senior's phone")
            else:
                self.events.action(call_id, "sms_failed", reason or "send_failed")

    def _purge_alerts(self) -> None:
        now = self._clock()
        for call_id, pending in list(self._pending_alerts.items()):
            if now - pending.queued_at >= TRUSTED_ALERT_TTL_SECONDS:
                del self._pending_alerts[call_id]
                log_event(logger, logging.WARNING, "trusted_alert_expired", call_id=call_id)
                if self.events is not None:
                    self.events.action(call_id, "sms_failed", "app_not_connected")
        for call_id, at in list(self._alerted.items()):
            if now - at >= _ALERT_MEMORY_SECONDS:
                del self._alerted[call_id]
                self._alert_results.discard(call_id)

    # ------------------------------------------------------------------ device settings
    def apply_settings(self, settings: DeviceSettings) -> None:
        self.device_settings = settings
        log_event(
            logger,
            logging.INFO,
            "app_settings_applied",
            lang=settings.lang,
            trusted_person=bool(settings.trusted_number),
            whitelist=len(settings.whitelist),
            ignored=settings.ignored,
        )

    def lang(self, default: Lang) -> Lang:
        return self.device_settings.lang if self.device_settings else default

    def is_whitelisted(self, number: str) -> bool:
        settings = self.device_settings
        return bool(settings and number and number in settings.whitelist)

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
