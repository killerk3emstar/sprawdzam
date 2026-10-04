"""Senior app WebSockets (protocol v0, docs/APP_PROTOCOL.md).

* `WS /app/control?device_token=...`: protection status, incoming-call notifications, ping.
* `WS /app/call/{callId}?token=...`: audio (binary PCM16 16 kHz) and call events (JSON).

Tokens arrive in the query string; `app.logging_setup.RedactTokensFilter` removes them from
the server's access logs.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re

from fastapi import APIRouter, WebSocket

from app.calls.sender import SafeSender
from app.logging_setup import log_event
from app.relay import protocol
from app.relay.device import DeviceSettings, InvalidSettings
from app.relay.protocol import BadAppMessage, parse_app_message
from app.services import get_services

logger = logging.getLogger(__name__)
router = APIRouter()

_CALL_ID_RE = re.compile(protocol.CALL_ID_PATTERN)


@router.websocket("/app/control")
async def control_channel(ws: WebSocket) -> None:
    hub = get_services(ws).hub
    await ws.accept()
    if not hub.check_device_token(ws.query_params.get("device_token", "")):
        log_event(
            logger, logging.WARNING, "app_control_rejected", configured=hub.device_token_configured
        )
        await ws.close(protocol.CLOSE_POLICY)
        return
    sender = SafeSender(ws)
    hub.add_control(sender)
    log_event(logger, logging.INFO, "app_control_connected", connections=hub.control_count)
    try:
        await sender.send_json(protocol.protection_status(True))
        await hub.deliver_pending_alerts(sender)
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive(), protocol.CONTROL_IDLE_TIMEOUT_SECONDS)
            except TimeoutError:
                log_event(logger, logging.INFO, "app_control_idle_timeout")
                await sender.close(protocol.CLOSE_IDLE)
                return
            if raw["type"] == "websocket.disconnect":
                return
            text = raw.get("text")
            if text is None:
                continue  # binary frames have no meaning on the control channel
            try:
                message = parse_app_message(text, protocol.MAX_CONTROL_TEXT_CHARS)
            except BadAppMessage as exc:
                log_event(logger, logging.WARNING, "app_control_bad_message", reason=str(exc))
                if '"settings"' in text:
                    await sender.send_json(protocol.settings_ack(False, error=str(exc)))
                continue
            if isinstance(message, protocol.Ping):
                await sender.send_json(protocol.pong())
            elif isinstance(message, protocol.AlertTrustedResult):
                hub.on_alert_result(message.callId, message.sent, message.error)
            elif isinstance(message, protocol.SettingsMessage):
                try:
                    settings = DeviceSettings.from_message(message)
                except InvalidSettings as exc:
                    log_event(logger, logging.WARNING, "app_settings_rejected", reason=str(exc))
                    await sender.send_json(protocol.settings_ack(False, error=str(exc)))
                    continue
                hub.apply_settings(settings)
                await sender.send_json(
                    protocol.settings_ack(True, len(settings.whitelist), settings.ignored)
                )
    finally:
        hub.remove_control(sender)
        log_event(logger, logging.INFO, "app_control_disconnected", connections=hub.control_count)


@router.websocket("/app/call/{call_id}")
async def call_channel(ws: WebSocket, call_id: str) -> None:
    hub = get_services(ws).hub
    await ws.accept()
    sender = SafeSender(ws)
    token = ws.query_params.get("token", "")
    bridge = hub.consume_token(call_id, token) if _CALL_ID_RE.fullmatch(call_id) else None
    if bridge is None or not bridge.attach_app(sender):
        log_event(
            logger,
            logging.WARNING,
            "app_call_rejected",
            call_id=call_id if _CALL_ID_RE.fullmatch(call_id) else None,
        )
        await sender.close(protocol.CLOSE_POLICY)
        return

    async def receive_loop() -> None:
        while True:
            raw = await ws.receive()
            if raw["type"] == "websocket.disconnect":
                return
            data = raw.get("bytes")
            if data is not None:
                await bridge.on_app_audio(data)
                continue
            try:
                message = parse_app_message(raw.get("text") or "")
            except BadAppMessage as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "app_call_bad_message",
                    call_id=call_id,
                    reason=str(exc),
                )
                continue
            if isinstance(message, protocol.Accept):
                await bridge.accept()
            elif isinstance(message, protocol.Hangup):
                await bridge.senior_hangup()
                return
            elif isinstance(message, protocol.Dtmf):
                bridge.on_dtmf(message.digits)
                log_event(logger, logging.INFO, "app_dtmf", call_id=call_id)

    receive = asyncio.create_task(receive_loop())
    ended = asyncio.create_task(bridge.ended.wait())
    try:
        await asyncio.wait({receive, ended}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (receive, ended):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if receive.done() and not receive.cancelled() and receive.exception() is not None:
            log_event(
                logger,
                logging.ERROR,
                "app_call_error",
                call_id=call_id,
                error_type=type(receive.exception()).__name__,
            )
        await bridge.app_detached()
        await sender.close(protocol.CLOSE_NORMAL)
