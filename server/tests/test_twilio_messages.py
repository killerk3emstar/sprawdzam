import base64

import numpy as np
import pytest
from pydantic import ValidationError

from app.twilio.messages import (
    MediaMessage,
    StartMessage,
    audio_to_media_messages,
    clear_message,
    inbound_adapter,
    mark_message,
)

STREAM_SID = "MZ" + "0" * 32
CALL_SID = "CA" + "1" * 32


def test_parses_twilio_start_message():
    message = inbound_adapter.validate_python(
        {
            "event": "start",
            "sequenceNumber": "1",
            "streamSid": STREAM_SID,
            "start": {
                "accountSid": "AC" + "a" * 32,
                "streamSid": STREAM_SID,
                "callSid": CALL_SID,
                "tracks": ["inbound"],
                "customParameters": {"token": "t", "lang": "en"},
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
            },
        }
    )
    assert isinstance(message, StartMessage)
    assert message.start.customParameters["lang"] == "en"


def test_media_payload_decoding():
    payload = base64.b64encode(b"\xff" * 160).decode()
    message = inbound_adapter.validate_python(
        {"event": "media", "streamSid": STREAM_SID, "media": {"payload": payload}}
    )
    assert isinstance(message, MediaMessage)
    assert message.media.track == "inbound"
    assert message.media.audio() == b"\xff" * 160


def test_invalid_base64_raises_value_error():
    message = inbound_adapter.validate_python(
        {"event": "media", "streamSid": STREAM_SID, "media": {"payload": "@@@"}}
    )
    with pytest.raises(ValueError):
        message.media.audio()


@pytest.mark.parametrize(
    "data",
    [
        {"event": "media", "streamSid": STREAM_SID},  # no media
        {"event": "media", "streamSid": "short", "media": {"payload": ""}},  # bad sid
        {"event": "start", "streamSid": STREAM_SID, "start": {"callSid": "x"}},
        {"event": "dtmf", "streamSid": STREAM_SID, "dtmf": {"digit": "55"}},
        {"event": "media", "streamSid": STREAM_SID, "media": {"payload": "A" * 20_000}},
        {"no_event": True},
        [1, 2, 3],
    ],
)
def test_rejects_malformed_messages(data):
    with pytest.raises(ValidationError):
        inbound_adapter.validate_python(data)


def test_outbound_builders():
    assert mark_message(STREAM_SID, "w1") == {
        "event": "mark",
        "streamSid": STREAM_SID,
        "mark": {"name": "w1"},
    }
    assert clear_message(STREAM_SID) == {"event": "clear", "streamSid": STREAM_SID}


def test_audio_to_media_messages_frames():
    one_second = np.zeros(16000, dtype=np.float32)
    messages = audio_to_media_messages(STREAM_SID, one_second, 16000)
    assert len(messages) == 50
    first = messages[0]
    assert first["event"] == "media"
    assert first["streamSid"] == STREAM_SID
    payload = base64.b64decode(first["media"]["payload"])
    assert len(payload) == 160
    assert set(payload) == {0xFF}  # silence in mu-law


def test_audio_to_media_messages_accepts_int16():
    pcm = (np.ones(8000) * 1000).astype(np.int16)
    messages = audio_to_media_messages(STREAM_SID, pcm, 8000)
    assert len(messages) == 50
