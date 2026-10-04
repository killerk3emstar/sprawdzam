"""Twilio implementation of `TelephonyProvider`."""

from __future__ import annotations

import base64
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass

import httpx
from pydantic import ValidationError
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.config import Lang, Settings
from app.logging_setup import log_event
from app.prompts import PROTECTION_NOTICE, PROTECTION_UNAVAILABLE, PROTECTION_UNAVAILABLE_NO_ROUTE
from app.telephony.provider import (
    IncomingCall,
    InvalidWebhook,
    MalformedStreamMessage,
    StreamConnected,
    StreamDtmf,
    StreamEvent,
    StreamMark,
    StreamMedia,
    StreamStarted,
    StreamStopped,
    WebhookAuth,
    WebhookForbidden,
)
from app.twilio.messages import (
    ConnectedMessage,
    DtmfMessage,
    MarkMessage,
    MediaMessage,
    StartMessage,
    StopMessage,
    inbound_adapter,
)
from app.twilio.rest import TwilioRest

logger = logging.getLogger(__name__)

CALL_SID_RE = re.compile(r"^CA[0-9a-f]{32}$")
ACCOUNT_SID_RE = re.compile(r"^AC[0-9a-f]{32}$")
KNOWN_EVENTS = {"connected", "start", "media", "mark", "dtmf", "stop"}


@dataclass(frozen=True)
class Voice:
    language: str  # BCP-47 tag for <Say language=...>
    voice: str  # Twilio <Say voice=...> (Amazon Polly voices)


VOICES: dict[Lang, Voice] = {
    "pl": Voice(language="pl-PL", voice="Polly.Ewa"),
    "en": Voice(language="en-US", voice="Polly.Joanna"),
}


class TwilioProvider:
    name = "twilio"
    markup_media_type = "application/xml"

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.rest = TwilioRest(settings, http_client)

    # ------------------------------------------------------------------ webhooks
    def verify_webhook(
        self, path: str, query: str, params: Mapping[str, object], headers: Mapping[str, str]
    ) -> WebhookAuth:
        """Validate X-Twilio-Signature against PUBLIC_BASE_URL + path (the app runs behind a
        tunnel or proxy, so the Host header and scheme it sees are not what Twilio signed)."""
        token = self.settings.twilio_auth_token
        if not token:
            if self.settings.ALLOW_UNSIGNED_WEBHOOKS:
                log_event(
                    logger,
                    logging.WARNING,
                    "twilio_signature_skipped",
                    reason="TWILIO_AUTH_TOKEN empty and ALLOW_UNSIGNED_WEBHOOKS=true",
                    path=path,
                )
                return WebhookAuth.SKIPPED_DEV
            return WebhookAuth.NOT_CONFIGURED
        signature = headers.get("x-twilio-signature")
        if not signature:
            return WebhookAuth.MISSING
        url = self.settings.public_url(path, query)
        valid = RequestValidator(token).validate(url, params, signature)
        return WebhookAuth.VALID if valid else WebhookAuth.INVALID

    def parse_incoming_call(self, params: Mapping[str, object]) -> IncomingCall:
        call_sid = str(params.get("CallSid") or "")
        if not CALL_SID_RE.fullmatch(call_sid):
            raise InvalidWebhook("missing or invalid CallSid")
        account_sid = str(params.get("AccountSid") or "")
        if account_sid and not ACCOUNT_SID_RE.fullmatch(account_sid):
            raise InvalidWebhook("invalid AccountSid")
        expected = self.settings.TWILIO_ACCOUNT_SID
        if expected and account_sid != expected:
            raise WebhookForbidden("account mismatch")
        caller = str(params.get("From") or "")[:64]
        return IncomingCall(call_id=call_sid, account_id=account_sid, caller=caller)

    def connect_markup(
        self, stream_url: str, lang: Lang, call_id: str, token: str, announce: bool = True
    ) -> str:
        voice = VOICES[lang]
        response = VoiceResponse()
        if announce:
            response.say(PROTECTION_NOTICE[lang], voice=voice.voice, language=voice.language)
        connect = Connect()
        stream = connect.stream(url=stream_url)
        stream.parameter(name="token", value=token)
        stream.parameter(name="lang", value=lang)
        stream.parameter(name="callId", value=call_id)
        response.append(connect)
        return str(response)

    def unavailable_markup(self, lang: Lang, dial_to: str | None = None) -> str:
        voice = VOICES[lang]
        response = VoiceResponse()
        if dial_to:
            response.say(PROTECTION_UNAVAILABLE[lang], voice=voice.voice, language=voice.language)
            response.dial(dial_to)
        else:
            text = PROTECTION_UNAVAILABLE_NO_ROUTE[lang]
            response.say(text, voice=voice.voice, language=voice.language)
            response.hangup()
        return str(response)

    # ------------------------------------------------------------------ media stream
    def verify_stream_handshake(self, url: str, headers: Mapping[str, str]) -> WebhookAuth:
        token = self.settings.twilio_auth_token
        if not token:
            return WebhookAuth.NOT_CONFIGURED
        signature = headers.get("x-twilio-signature")
        if not signature:
            return WebhookAuth.MISSING
        valid = RequestValidator(token).validate(url, {}, signature)
        return WebhookAuth.VALID if valid else WebhookAuth.INVALID

    def parse_stream_message(self, data: object) -> StreamEvent | None:
        if isinstance(data, dict) and data.get("event") not in KNOWN_EVENTS:
            return None  # unknown events are allowed by the protocol: skip
        try:
            message = inbound_adapter.validate_python(data)
        except ValidationError as exc:
            errors = exc.errors(include_input=False, include_url=False)
            raise MalformedStreamMessage(
                "schema", [{"loc": list(e["loc"]), "type": e["type"]} for e in errors[:5]]
            ) from None
        match message:
            case MediaMessage():
                try:
                    audio = message.media.audio()
                except ValueError:
                    raise MalformedStreamMessage("invalid_base64") from None
                track = (
                    "inbound"
                    if message.media.track in ("inbound", "inbound_track")
                    else (message.media.track)
                )
                return StreamMedia(message.streamSid, track, audio)
            case StartMessage():
                info = message.start
                if info.streamSid != message.streamSid:
                    raise MalformedStreamMessage("stream_sid_mismatch")
                fmt = info.mediaFormat
                return StreamStarted(
                    stream_id=message.streamSid,
                    call_id=info.callSid,
                    params=dict(info.customParameters),
                    encoding=fmt.encoding if fmt else None,
                    sample_rate=fmt.sampleRate if fmt else None,
                    channels=fmt.channels if fmt else None,
                )
            case ConnectedMessage():
                return StreamConnected()
            case MarkMessage():
                return StreamMark(message.streamSid, message.mark.name)
            case DtmfMessage():
                return StreamDtmf(message.streamSid, message.dtmf.digit)
            case StopMessage():
                return StreamStopped(message.streamSid)
        return None  # pragma: no cover - the union above is exhaustive

    def media_message(self, stream_id: str, mulaw: bytes) -> dict[str, object]:
        return {
            "event": "media",
            "streamSid": stream_id,
            "media": {"payload": base64.b64encode(mulaw).decode("ascii")},
        }

    def mark_message(self, stream_id: str, name: str) -> dict[str, object]:
        return {"event": "mark", "streamSid": stream_id, "mark": {"name": name}}

    def clear_message(self, stream_id: str) -> dict[str, object]:
        return {"event": "clear", "streamSid": stream_id}

    # ------------------------------------------------------------------ REST
    async def hang_up(self, call_sid: str) -> object:
        return await self.rest.hang_up(call_sid)

    async def call_trusted_person(
        self, call_sid: str, to: str, message: str, lang: Lang = "pl"
    ) -> object:
        voice = VOICES[lang]
        response = VoiceResponse()
        response.say(message, voice=voice.voice, language=voice.language)
        response.pause(length=1)
        response.say(message, voice=voice.voice, language=voice.language)
        return await self.rest.create_call(to, str(response))

    async def send_sms(self, call_sid: str, to: str, body: str) -> object:
        return await self.rest.send_sms(to, body)
