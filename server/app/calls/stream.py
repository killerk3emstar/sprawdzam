"""`WS /<provider>/stream`: provider media stream for one call (Twilio: `/twilio/stream`).

Protocol (provider-neutral events): connected -> start -> many media (+ mark, dtmf) -> stop.

Safety:
* The start event must carry the one-time token issued by the voice webhook for the same
  call id (`<Parameter name="token">`); otherwise the socket is closed (1008).
* No start within START_TIMEOUT seconds -> closed.
* Malformed messages are logged (error type and field only, never payloads) and skipped;
  more than MAX_MALFORMED of them close the stream.
* After MAX_CALL_SECONDS the server closes the socket. Closing ends `<Connect>`; as there is
  no further TwiML verb, the provider hangs up the call. The same mechanism ends the call
  when the bridge ends it (senior hung up, not answered, scam blocked).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import WebSocket

from app.audio.resample import STT_RATE
from app.audio.segmenter import PauseSegmenter
from app.calls.bridge import CallBridge
from app.calls.sender import SafeSender
from app.logging_setup import log_event
from app.relay.device import choose_trusted_number
from app.relay.protocol import EndReason
from app.services import Services, get_services
from app.session import CallSession
from app.telephony.numbers import mask_caller
from app.telephony.provider import (
    MalformedStreamMessage,
    StreamDtmf,
    StreamEvent,
    StreamMark,
    StreamMedia,
    StreamStarted,
    StreamStopped,
)
from app.telephony.responder import IncidentResponder

logger = logging.getLogger(__name__)

START_TIMEOUT = 10.0
MAX_MALFORMED = 50
MAX_MESSAGE_CHARS = 32_000
MAX_FRAME_BYTES = 8000  # 1 s of mu-law audio; providers send 160-byte frames

CLOSE_NORMAL = 1000
CLOSE_UNSUPPORTED = 1003
CLOSE_POLICY = 1008


class _StreamEnded(Exception):
    def __init__(self, reason: EndReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class StreamHandler:
    def __init__(self, ws: WebSocket, services: Services) -> None:
        self.ws = ws
        self.services = services
        self.settings = services.settings
        self.provider = services.provider
        self.out = SafeSender(ws)
        self.session: CallSession | None = None
        self.bridge: CallBridge | None = None
        self.malformed = 0

    # ------------------------------------------------------------------ main flow
    async def run(self) -> None:
        await self.ws.accept()
        self._log_handshake_signature()
        reason = EndReason.ERROR
        try:
            if await self._wait_for_start():
                reason = await self._run_call()
        except _StreamEnded as exc:
            reason = exc.reason
        except Exception as exc:  # noqa: BLE001 - log, then clean up below
            log_event(
                logger,
                logging.ERROR,
                "stream_error",
                error_type=type(exc).__name__,
                call_id=self.session.call_sid if self.session else None,
            )
        finally:
            await self._cleanup(reason)

    async def _wait_for_start(self) -> bool:
        try:
            async with asyncio.timeout(START_TIMEOUT):
                while True:
                    event = await self._next_event()
                    if isinstance(event, StreamStarted):
                        return await self._handle_start(event)
                    if isinstance(event, StreamStopped):
                        return False
                    # `connected` is expected; anything else before `start` is ignored.
        except TimeoutError:
            log_event(logger, logging.WARNING, "stream_start_timeout")
            await self.out.close(CLOSE_POLICY)
            return False

    async def _run_call(self) -> EndReason:
        bridge = self.bridge
        if bridge is None:  # pragma: no cover - only called after a successful start
            return EndReason.ERROR
        receive = asyncio.create_task(self._receive_loop())
        ended = asyncio.create_task(bridge.ended.wait())
        try:
            done, _ = await asyncio.wait(
                {receive, ended},
                timeout=self.settings.MAX_CALL_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (receive, ended):
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
        if receive in done:
            exc = receive.exception()
            if exc is None:
                return EndReason.CALLER_HANGUP  # provider sent stop
            if isinstance(exc, _StreamEnded):
                return exc.reason
            raise exc
        if ended in done:
            return bridge.end_reason or EndReason.ERROR
        log_event(
            logger,
            logging.INFO,
            "max_call_duration_reached",
            call_id=bridge.call_id,
            max_seconds=self.settings.MAX_CALL_SECONDS,
        )
        return EndReason.TIMEOUT

    async def _receive_loop(self) -> None:
        session, bridge = self.session, self.bridge
        if session is None or bridge is None:  # pragma: no cover - only after start
            return
        while True:
            event = await self._next_event()
            if isinstance(event, StreamMedia):
                if event.stream_id != bridge.stream_id:
                    self._malformed("stream_id_mismatch")
                elif event.track != "inbound":
                    continue  # only the caller's audio is analysed and forwarded
                elif len(event.audio) > MAX_FRAME_BYTES:
                    self._malformed("frame_too_large")
                else:
                    await bridge.on_caller_audio(session.feed_mulaw(event.audio))
            elif isinstance(event, StreamStopped):
                log_event(logger, logging.INFO, "stream_stop", call_id=session.call_sid)
                return
            elif isinstance(event, StreamDtmf):
                bridge.on_dtmf(event.digit)
                log_event(logger, logging.INFO, "stream_dtmf", call_id=session.call_sid)
            elif isinstance(event, StreamMark):
                log_event(logger, logging.DEBUG, "stream_mark", call_id=session.call_sid)
            elif isinstance(event, StreamStarted):
                self._malformed("duplicate_start")

    # ------------------------------------------------------------------ messages
    async def _next_event(self) -> StreamEvent:
        while True:
            raw = await self.ws.receive()
            if raw["type"] == "websocket.disconnect":
                raise _StreamEnded(EndReason.CALLER_HANGUP)
            text = raw.get("text")
            if text is None:
                self._malformed("binary_frame")
                continue
            if len(text) > MAX_MESSAGE_CHARS:
                self._malformed("message_too_large")
                continue
            try:
                data = json.loads(text)
            except ValueError:
                self._malformed("invalid_json")
                continue
            try:
                event = self.provider.parse_stream_message(data)
            except MalformedStreamMessage as exc:
                self._malformed(exc.reason, exc.errors)
                continue
            if event is None:
                log_event(logger, logging.DEBUG, "stream_unknown_event")
                continue
            return event

    def _malformed(self, reason: str, errors: list[dict[str, object]] | None = None) -> None:
        self.malformed += 1
        call_id = self.session.call_sid if self.session else None
        log_event(
            logger,
            logging.WARNING,
            "stream_malformed_message",
            call_id=call_id,
            reason=reason,
            errors=errors,
            count=self.malformed,
        )
        if self.malformed > MAX_MALFORMED:
            log_event(logger, logging.WARNING, "stream_too_many_malformed", call_id=call_id)
            raise _StreamEnded(EndReason.ERROR)

    async def _handle_start(self, event: StreamStarted) -> bool:
        services = self.services
        call_id = event.call_id
        admitted = services.admission.activate(call_id, event.params.get("token", ""))
        if admitted is None:
            log_event(
                logger,
                logging.WARNING,
                "stream_rejected",
                call_id=call_id,
                reason="invalid_token_or_capacity",
            )
            await self.out.close(CLOSE_POLICY)
            return False
        if (event.encoding, event.sample_rate, event.channels) not in {
            (None, None, None),
            ("audio/x-mulaw", 8000, 1),
        }:
            log_event(
                logger,
                logging.WARNING,
                "stream_unsupported_format",
                call_id=call_id,
                encoding=event.encoding,
                rate=event.sample_rate,
                channels=event.channels,
            )
            services.admission.release(call_id)
            await self.out.close(CLOSE_UNSUPPORTED)
            return False
        if not services.hub.online:
            # The app went away between the webhook and the stream start: end the call.
            log_event(logger, logging.WARNING, "stream_rejected", call_id=call_id, reason="no_app")
            services.admission.release(call_id)
            await self.out.close(CLOSE_NORMAL)
            return False

        lang = admitted.lang
        # Contacts on the senior's whitelist are bridged without speech-to-text or risk
        # analysis (CLAUDE.md: contacts are never analysed).
        trusted = services.hub.is_whitelisted(admitted.caller)
        bridge = CallBridge(
            call_id=call_id,
            stream_id=event.stream_id,
            lang=lang,
            caller_display=mask_caller(admitted.caller),
            trusted=trusted,
            provider=self.provider,
            provider_out=self.out,
            hub=services.hub,
            accept_timeout=self.settings.APP_ACCEPT_TIMEOUT_SECONDS,
            password_timeout=self.settings.PASSWORD_TIMEOUT_SECONDS,
            auto_block_seconds=self.settings.AUTO_BLOCK_SECONDS,
            family_password=self.settings.FAMILY_PASSWORD.get_secret_value(),
            prompts=services.prompts,
            events=services.events,
        )
        trusted_number = choose_trusted_number(
            services.hub.device_settings,
            self.settings.TRUSTED_PERSON_NUMBER,
            self.settings.outbound_allowlist,
        )
        responder = IncidentResponder(bridge, services.actions, lang, trusted_number)
        bridge.on_senior_blocked = responder.after_senior_block
        session = CallSession(
            call_sid=call_id,
            stream_sid=event.stream_id,
            lang=lang,
            stt=services.stt,
            monitor=services.engine.start_call(call_id, lang, responder),
            segmenter=PauseSegmenter(
                STT_RATE,
                min_seconds=self.settings.STT_MIN_SEGMENT_SECONDS,
                max_seconds=self.settings.STT_MAX_SEGMENT_SECONDS,
                pause_seconds=self.settings.STT_PAUSE_SECONDS,
            ),
            senior_segmenter=PauseSegmenter(
                STT_RATE,
                min_seconds=self.settings.STT_SENIOR_MIN_SEGMENT_SECONDS,
                max_seconds=self.settings.STT_MAX_SEGMENT_SECONDS,
                pause_seconds=self.settings.STT_PAUSE_SECONDS,
            ),
            stt_timeout=self.settings.STT_TIMEOUT_SECONDS,
            analyse=not trusted,
            analyse_senior=self.settings.ANALYSE_SENIOR,
            events=services.events,
        )
        bridge.senior_audio_sink = session.feed_senior_pcm16
        bridge.played_text_sink = session.echo_guard.add_caller
        session.start()
        self.session, self.bridge = session, bridge
        services.sessions[call_id] = session
        log_event(
            logger,
            logging.INFO,
            "stream_started",
            call_id=call_id,
            lang=lang,
            provider=self.provider.name,
            trusted_caller=trusted,
        )
        await bridge.start()
        return True

    # ------------------------------------------------------------------ helpers
    def _log_handshake_signature(self) -> None:
        """Logged, not enforced, until verified against a real provider account; the
        per-call token is the enforced check."""
        query = self.ws.url.query
        url = self.settings.ws_url(self.ws.url.path) + (f"?{query}" if query else "")
        status = self.provider.verify_stream_handshake(url, self.ws.headers)
        log_event(logger, logging.DEBUG, "stream_handshake_signature", status=status.value)

    async def _cleanup(self, reason: EndReason) -> None:
        session, bridge = self.session, self.bridge
        if session is not None:
            # Free the slot first (synchronously) so it is released even if we get cancelled.
            self.services.sessions.pop(session.call_sid, None)
            self.services.admission.release(session.call_sid)
        try:
            if bridge is not None:
                await bridge.end(reason)
            if session is not None:
                await session.close()
            if bridge is not None:
                await bridge.wait_background()
        finally:
            await self.out.close(CLOSE_NORMAL)


async def media_stream(ws: WebSocket) -> None:
    await StreamHandler(ws, get_services(ws)).run()
