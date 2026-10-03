"""`WS /twilio/stream`: Twilio bidirectional Media Stream for one call.

Protocol: `connected` -> `start` -> many `media` (+ `mark`, `dtmf`) -> `stop`.

Safety:
* The `start` message must carry the one-time token issued by `/twilio/voice` for the same
  CallSid (TwiML `<Parameter name="token">`); otherwise the socket is closed (1008).
* No `start` within START_TIMEOUT seconds -> closed.
* Malformed messages are logged (error type and field only, never payloads) and skipped;
  more than MAX_MALFORMED of them close the stream.
* After MAX_CALL_SECONDS the server closes the socket. That ends `<Connect>`; as there is
  no further TwiML verb, Twilio hangs up the call.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

import numpy as np
from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketState
from twilio.request_validator import RequestValidator

from app.config import Lang
from app.logging_setup import log_event
from app.services import Services, get_services
from app.session import CallSession
from app.telephony.responder import IncidentResponder
from app.twilio.messages import (
    MAX_MESSAGE_CHARS,
    DtmfMessage,
    InboundMessage,
    MarkMessage,
    MediaMessage,
    StartMessage,
    StopMessage,
    audio_to_media_messages,
    inbound_adapter,
    mark_message,
)

logger = logging.getLogger(__name__)
router = APIRouter()

START_TIMEOUT = 10.0
MAX_MALFORMED = 50
MAX_FRAME_BYTES = 8000  # 1 s of mu-law audio; Twilio sends 160-byte frames

CLOSE_NORMAL = 1000
CLOSE_UNSUPPORTED = 1003
CLOSE_POLICY = 1008


class _StreamClosed(Exception):
    """Client disconnected or the stream must end."""


class StreamHandler:
    def __init__(self, ws: WebSocket, services: Services) -> None:
        self.ws = ws
        self.services = services
        self.settings = services.settings
        self.session: CallSession | None = None
        self.malformed = 0

    # ------------------------------------------------------------------ main flow
    async def run(self) -> None:
        await self.ws.accept()
        self._log_handshake_signature()
        try:
            session = await self._wait_for_start()
            if session is None:
                return
            limit = asyncio.timeout(self.settings.MAX_CALL_SECONDS)
            try:
                async with limit:
                    await self._receive_loop(session)
            except TimeoutError:
                if not limit.expired():
                    raise
                log_event(
                    logger,
                    logging.INFO,
                    "max_call_duration_reached",
                    call_id=session.call_sid,
                    max_seconds=self.settings.MAX_CALL_SECONDS,
                )
        except _StreamClosed:
            pass
        finally:
            await self._cleanup()

    async def _wait_for_start(self) -> CallSession | None:
        try:
            async with asyncio.timeout(START_TIMEOUT):
                while True:
                    message = await self._next_message()
                    if message is None:
                        continue
                    if isinstance(message, StartMessage):
                        return await self._handle_start(message)
                    if isinstance(message, StopMessage):
                        return None
                    # `connected` is expected; anything else before `start` is ignored.
        except TimeoutError:
            log_event(logger, logging.WARNING, "stream_start_timeout")
            await self._close(CLOSE_POLICY)
            return None

    async def _receive_loop(self, session: CallSession) -> None:
        while True:
            message = await self._next_message()
            if message is None:
                continue
            if isinstance(message, MediaMessage):
                self._handle_media(session, message)
            elif isinstance(message, StopMessage):
                log_event(logger, logging.INFO, "stream_stop", call_id=session.call_sid)
                return
            elif isinstance(message, MarkMessage):
                log_event(logger, logging.DEBUG, "stream_mark", call_id=session.call_sid)
            elif isinstance(message, DtmfMessage):
                session.on_dtmf(message.dtmf.digit)
                log_event(logger, logging.INFO, "stream_dtmf", call_id=session.call_sid)
            elif isinstance(message, StartMessage):
                self._malformed("duplicate_start")

    # ------------------------------------------------------------------ messages
    async def _next_message(self) -> InboundMessage | None:
        raw = await self.ws.receive()
        if raw["type"] == "websocket.disconnect":
            raise _StreamClosed
        text = raw.get("text")
        if text is None:
            self._malformed("binary_frame")
            return None
        if len(text) > MAX_MESSAGE_CHARS:
            self._malformed("message_too_large")
            return None
        try:
            data = json.loads(text)
        except ValueError:
            self._malformed("invalid_json")
            return None
        if isinstance(data, dict) and data.get("event") not in {
            "connected",
            "start",
            "media",
            "mark",
            "dtmf",
            "stop",
        }:
            # Unknown events are allowed by the protocol (forward compatibility): skip quietly.
            log_event(logger, logging.DEBUG, "stream_unknown_event")
            return None
        try:
            return inbound_adapter.validate_python(data)
        except ValidationError as exc:
            errors = exc.errors(include_input=False, include_url=False)
            self._malformed(
                "schema", [{"loc": list(e["loc"]), "type": e["type"]} for e in errors[:5]]
            )
            return None

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
            raise _StreamClosed

    async def _handle_start(self, message: StartMessage) -> CallSession | None:
        info = message.start
        call_sid = info.callSid
        params = info.customParameters
        if info.streamSid != message.streamSid:
            self._malformed("stream_sid_mismatch")
            await self._close(CLOSE_POLICY)
            return None
        if not self.services.admission.activate(call_sid, params.get("token", "")):
            log_event(
                logger,
                logging.WARNING,
                "stream_rejected",
                call_id=call_sid,
                reason="invalid_token_or_capacity",
            )
            await self._close(CLOSE_POLICY)
            return None
        fmt = info.mediaFormat
        if fmt is not None and (
            fmt.encoding != "audio/x-mulaw" or fmt.sampleRate != 8000 or fmt.channels != 1
        ):
            log_event(
                logger,
                logging.WARNING,
                "stream_unsupported_format",
                call_id=call_sid,
                encoding=fmt.encoding,
                rate=fmt.sampleRate,
                channels=fmt.channels,
            )
            self.services.admission.release(call_sid)
            await self._close(CLOSE_UNSUPPORTED)
            return None

        lang: Lang = self.settings.DEFAULT_LANG
        if params.get("lang") in ("pl", "en"):
            lang = params["lang"]  # type: ignore[assignment]
        responder = IncidentResponder(
            self.services.actions, lang, self.settings.TRUSTED_PERSON_NUMBER
        )
        session = CallSession(
            call_sid=call_sid,
            stream_sid=message.streamSid,
            lang=lang,
            stt=self.services.stt,
            monitor=self.services.engine.start_call(call_sid, lang, responder),
            window_seconds=self.settings.STT_WINDOW_SECONDS,
            stt_timeout=self.settings.STT_TIMEOUT_SECONDS,
        )
        session.start()
        self.session = session
        self.services.sessions[call_sid] = session
        log_event(logger, logging.INFO, "stream_started", call_id=call_sid, lang=lang)
        return session

    def _handle_media(self, session: CallSession, message: MediaMessage) -> None:
        if message.streamSid != session.stream_sid:
            self._malformed("stream_sid_mismatch")
            return
        if message.media.track not in ("inbound", "inbound_track"):
            return  # only the caller's audio is analysed
        try:
            audio = message.media.audio()
        except ValueError:
            self._malformed("invalid_base64")
            return
        if len(audio) > MAX_FRAME_BYTES:
            self._malformed("frame_too_large")
            return
        session.feed_mulaw(audio)

    # ------------------------------------------------------------------ helpers
    def _log_handshake_signature(self) -> None:
        """Log (do not enforce) the handshake signature until verified against real Twilio;
        the per-call token is the enforced check."""
        signature = self.ws.headers.get("x-twilio-signature")
        token = self.settings.twilio_auth_token
        if not signature or not token:
            status = "absent" if not signature else "no_auth_token"
        else:
            query = self.ws.url.query
            url = self.settings.stream_url + (f"?{query}" if query else "")
            status = "valid" if RequestValidator(token).validate(url, {}, signature) else "invalid"
        log_event(logger, logging.DEBUG, "stream_handshake_signature", status=status)

    async def _close(self, code: int) -> None:
        if (
            self.ws.application_state == WebSocketState.CONNECTED
            and self.ws.client_state == WebSocketState.CONNECTED
        ):
            with contextlib.suppress(RuntimeError):  # client went away in the meantime
                await self.ws.close(code)

    async def _cleanup(self) -> None:
        session = self.session
        if session is not None:
            # Free the slot first (synchronously) so it is released even if we get cancelled.
            self.services.sessions.pop(session.call_sid, None)
            self.services.admission.release(session.call_sid)
            await session.close()
        await self._close(CLOSE_NORMAL)


@router.websocket("/twilio/stream")
async def media_stream(ws: WebSocket) -> None:
    await StreamHandler(ws, get_services(ws)).run()


async def send_audio(
    ws: WebSocket,
    stream_sid: str,
    audio: np.ndarray,
    sample_rate: int,
    mark: str | None = None,
) -> None:
    """Play audio to the caller (e.g. a voice warning): PCM -> mu-law 8 kHz `media` messages,
    followed by an optional `mark` so we learn when playback finished."""
    for message in audio_to_media_messages(stream_sid, audio, sample_rate):
        await ws.send_json(message)
    if mark:
        await ws.send_json(mark_message(stream_sid, mark))
