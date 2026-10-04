"""Twilio Media Streams WebSocket messages (inbound validation models).

Reference: https://www.twilio.com/docs/voice/media-streams/websocket-messages
"""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

Sid = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}[0-9a-fA-F]{32}$")]
ShortStr = Annotated[str, StringConstraints(max_length=256)]

# Twilio sends 20 ms frames (160 bytes, ~216 base64 chars); allow generous headroom.
MAX_MEDIA_PAYLOAD_CHARS = 16_000
MAX_MESSAGE_CHARS = 32_000
MAX_CUSTOM_PARAMETERS = 16


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class ConnectedMessage(_Msg):
    event: Literal["connected"]
    protocol: ShortStr | None = None
    version: ShortStr | None = None


class MediaFormat(_Msg):
    encoding: ShortStr
    sampleRate: int
    channels: int


class StartInfo(_Msg):
    streamSid: Sid
    callSid: Sid
    accountSid: Sid | None = None
    tracks: list[ShortStr] = Field(default_factory=list, max_length=4)
    customParameters: dict[ShortStr, ShortStr] = Field(
        default_factory=dict, max_length=MAX_CUSTOM_PARAMETERS
    )
    mediaFormat: MediaFormat | None = None


class StartMessage(_Msg):
    event: Literal["start"]
    streamSid: Sid
    start: StartInfo


class MediaInfo(_Msg):
    track: ShortStr = "inbound"
    payload: Annotated[str, StringConstraints(max_length=MAX_MEDIA_PAYLOAD_CHARS)]
    chunk: ShortStr | None = None
    timestamp: ShortStr | None = None

    def audio(self) -> bytes:
        """Decode the base64 payload. Raises ValueError on invalid base64."""
        try:
            return base64.b64decode(self.payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("invalid base64 media payload") from exc


class MediaMessage(_Msg):
    event: Literal["media"]
    streamSid: Sid
    media: MediaInfo


class MarkInfo(_Msg):
    name: ShortStr


class MarkMessage(_Msg):
    event: Literal["mark"]
    streamSid: Sid
    mark: MarkInfo


class DtmfInfo(_Msg):
    track: ShortStr | None = None
    digit: Annotated[str, StringConstraints(pattern=r"^[0-9*#A-D]$")]


class DtmfMessage(_Msg):
    event: Literal["dtmf"]
    streamSid: Sid
    dtmf: DtmfInfo


class StopMessage(_Msg):
    event: Literal["stop"]
    streamSid: Sid


InboundMessage = Annotated[
    ConnectedMessage | StartMessage | MediaMessage | MarkMessage | DtmfMessage | StopMessage,
    Field(discriminator="event"),
]
inbound_adapter: TypeAdapter[InboundMessage] = TypeAdapter(InboundMessage)
