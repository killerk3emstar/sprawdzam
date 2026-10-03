"""Twilio Media Streams WebSocket messages: validation of inbound, builders for outbound.

Reference: https://www.twilio.com/docs/voice/media-streams/websocket-messages
"""

from __future__ import annotations

import base64
import binascii
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

from app.audio.g711 import mulaw_encode
from app.audio.resample import TWILIO_RATE, resample

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


# ---------------------------------------------------------------------- outbound builders
def media_message(stream_sid: str, mulaw: bytes) -> dict[str, object]:
    return {
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": base64.b64encode(mulaw).decode("ascii")},
    }


def mark_message(stream_sid: str, name: str) -> dict[str, object]:
    return {"event": "mark", "streamSid": stream_sid, "mark": {"name": name}}


def clear_message(stream_sid: str) -> dict[str, object]:
    return {"event": "clear", "streamSid": stream_sid}


def audio_to_media_messages(
    stream_sid: str,
    audio: np.ndarray,
    sample_rate: int,
    frame_ms: int = 20,
) -> list[dict[str, object]]:
    """Convert PCM (int16 or float32 in [-1, 1]) at any rate into Twilio `media` messages
    with mu-law 8 kHz payloads, split into `frame_ms` frames."""
    samples = np.asarray(audio)
    if np.issubdtype(samples.dtype, np.integer):
        samples = samples.astype(np.float32) / 32768.0
    samples = resample(samples, sample_rate, TWILIO_RATE)
    mulaw = mulaw_encode(samples)
    step = TWILIO_RATE * frame_ms // 1000
    return [media_message(stream_sid, mulaw[i : i + step]) for i in range(0, len(mulaw), step)]
