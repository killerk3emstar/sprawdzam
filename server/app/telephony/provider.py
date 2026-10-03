"""Telephony provider interface.

Everything that differs between Twilio, SignalWire and similar providers sits behind
`TelephonyProvider`: webhook authentication and parsing, call-control markup (TwiML/cXML),
media-stream message parsing and encoding, and the REST actions that can spend money (the
latter are always wrapped in `GuardedCallActions`).

The rest of the backend works with the provider-neutral types below.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from app.config import Lang


class WebhookAuth(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING = "missing"
    NOT_CONFIGURED = "not_configured"  # no signing secret and unsigned webhooks not allowed
    SKIPPED_DEV = "skipped_dev"  # no signing secret, ALLOW_UNSIGNED_WEBHOOKS=true

    @property
    def accepted(self) -> bool:
        return self in (WebhookAuth.VALID, WebhookAuth.SKIPPED_DEV)


class InvalidWebhook(ValueError):
    """The webhook body is authentic but its fields are missing or malformed (HTTP 400)."""


class WebhookForbidden(InvalidWebhook):
    """Authentic but not for us, e.g. another provider account (HTTP 403)."""


@dataclass(frozen=True)
class IncomingCall:
    call_id: str
    account_id: str  # "" when the provider did not send one
    caller: str  # caller number as sent by the provider (RAM only, never logged)


# ---------------------------------------------------------------------- media stream events
@dataclass(frozen=True)
class StreamConnected:
    pass


@dataclass(frozen=True)
class StreamStarted:
    stream_id: str
    call_id: str
    params: dict[str, str] = field(default_factory=dict)
    encoding: str | None = None  # None when the provider did not say
    sample_rate: int | None = None
    channels: int | None = None


@dataclass(frozen=True)
class StreamMedia:
    stream_id: str
    track: str  # "inbound" (caller) or "outbound"
    audio: bytes  # mu-law 8 kHz


@dataclass(frozen=True)
class StreamMark:
    stream_id: str
    name: str


@dataclass(frozen=True)
class StreamDtmf:
    stream_id: str
    digit: str


@dataclass(frozen=True)
class StreamStopped:
    stream_id: str


StreamEvent = (
    StreamConnected | StreamStarted | StreamMedia | StreamMark | StreamDtmf | StreamStopped
)


class MalformedStreamMessage(ValueError):
    def __init__(self, reason: str, errors: list[dict[str, object]] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.errors = errors


@runtime_checkable
class TelephonyProvider(Protocol):
    # Also the URL prefix: POST /<name>/voice, WS /<name>/stream.
    name: str
    markup_media_type: str

    # ---- webhooks
    def verify_webhook(
        self, path: str, query: str, params: Mapping[str, object], headers: Mapping[str, str]
    ) -> WebhookAuth: ...

    def parse_incoming_call(self, params: Mapping[str, object]) -> IncomingCall:
        """Raises InvalidWebhook / WebhookForbidden."""
        ...

    def connect_markup(self, stream_url: str, lang: Lang, call_id: str, token: str) -> str:
        """Protection notice, then connect the call audio to our media stream WebSocket."""
        ...

    def unavailable_markup(self, lang: Lang) -> str:
        """'Protection temporarily unavailable', then hang up."""
        ...

    # ---- media stream
    def verify_stream_handshake(self, url: str, headers: Mapping[str, str]) -> WebhookAuth: ...

    def parse_stream_message(self, data: object) -> StreamEvent | None:
        """Decoded JSON -> event. None for unknown events (skip quietly).
        Raises MalformedStreamMessage."""
        ...

    def media_message(self, stream_id: str, mulaw: bytes) -> dict[str, object]: ...

    def mark_message(self, stream_id: str, name: str) -> dict[str, object]: ...

    def clear_message(self, stream_id: str) -> dict[str, object]: ...

    # ---- REST actions (spend money; only ever called through GuardedCallActions)
    async def hang_up(self, call_sid: str) -> object: ...

    async def call_trusted_person(
        self, call_sid: str, to: str, message: str, lang: Lang = "pl"
    ) -> object: ...

    async def send_sms(self, call_sid: str, to: str, body: str) -> object: ...
