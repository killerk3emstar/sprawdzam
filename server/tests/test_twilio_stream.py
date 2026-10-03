import json
import logging
import time
import xml.etree.ElementTree as ET

import pytest

from app.twilio import stream as stream_module
from tests.conftest import (
    CALL_SID,
    STREAM_SID,
    FakeSTT,
    RecordingActions,
    post_voice,
    tone_mulaw_frames,
    voice_params,
)

SCAM_TEXT = (
    "Mówi komisarz z CBŚ. Proszę wypłacić gotówkę i przekazać ją kurierowi. Nikomu o tym nie mówić."
)


def admit(client, call_sid: str = CALL_SID) -> str:
    root = ET.fromstring(post_voice(client, voice_params(call_sid=call_sid)).text)
    params = {p.get("name"): p.get("value") for p in root.findall("Connect/Stream/Parameter")}
    return params["token"]


def start_message(token: str, call_sid: str = CALL_SID, **media_format) -> dict:
    fmt = {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}
    fmt.update(media_format)
    return {
        "event": "start",
        "sequenceNumber": "1",
        "streamSid": STREAM_SID,
        "start": {
            "accountSid": "AC" + "a" * 32,
            "streamSid": STREAM_SID,
            "callSid": call_sid,
            "tracks": ["inbound"],
            "customParameters": {"token": token, "lang": "pl", "callId": call_sid},
            "mediaFormat": fmt,
        },
    }


def media(payload: str, track: str = "inbound") -> dict:
    return {
        "event": "media",
        "streamSid": STREAM_SID,
        "media": {"track": track, "chunk": "1", "timestamp": "0", "payload": payload},
    }


def stop_message() -> dict:
    return {
        "event": "stop",
        "streamSid": STREAM_SID,
        "stop": {"accountSid": "AC" + "a" * 32, "callSid": CALL_SID},
    }


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_full_stream_flow_with_malformed_messages(make_client, caplog):
    caplog.set_level(logging.INFO)
    stt = FakeSTT([SCAM_TEXT])
    inner = RecordingActions()
    client = make_client(stt=stt, inner_actions=inner)
    services = client.app.state.services
    token = admit(client)
    frames = tone_mulaw_frames(6.5)  # two full 3 s windows

    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json({"event": "connected", "protocol": "Call", "version": "1.0.0"})
        ws.send_json(start_message(token))
        for payload in frames[:100]:
            ws.send_json(media(payload))
        # Malformed input must be skipped without ending the call.
        ws.send_text("{this is not json")
        ws.send_json({"event": "media", "streamSid": STREAM_SID, "media": {"track": "inbound"}})
        ws.send_json(media("!!!not-base64!!!"))
        ws.send_json({"event": "media", "streamSid": "bad", "media": {"payload": frames[0]}})
        ws.send_bytes(b"\x00\x01")
        ws.send_json({"event": "something_new"})
        ws.send_json(media(frames[0], track="outbound"))  # ignored, not the caller
        ws.send_json({"event": "mark", "streamSid": STREAM_SID, "mark": {"name": "warning"}})
        ws.send_json(
            {
                "event": "dtmf",
                "streamSid": STREAM_SID,
                "dtmf": {"track": "inbound_track", "digit": "5"},
            }
        )
        for payload in frames[100:]:
            ws.send_json(media(payload))
        assert wait_until(lambda: CALL_SID in services.sessions)
        ws.send_json(stop_message())
        closing = ws.receive()
        assert closing["type"] == "websocket.close"

    # STT got two 3 s windows of 16 kHz float32 audio in the call language.
    assert [c[:3] for c in stt.calls] == [(48000, 16000, "pl"), (48000, 16000, "pl")]
    assert all(str(c[3]) == "float32" for c in stt.calls)
    # Window 1 -> warning; window 2 -> sustained high risk -> hang-up (dry run: not executed).
    assert inner.kinds() == ["warn"]
    messages = "\n".join(r.getMessage() for r in caplog.records)
    assert "telephony_would_hang_up" in messages
    assert messages.count("stream_malformed_message") == 5
    # Everything is cleaned up after `stop`.
    assert services.sessions == {}
    assert services.admission.active_count == 0
    # Privacy: no transcript text and no DTMF digit in the logs.
    assert "komisarz" not in messages and "kurierowi" not in messages
    assert '"digit"' not in messages


def test_invalid_token_is_refused(make_client):
    client = make_client(stt=FakeSTT())
    admit(client)
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json({"event": "connected"})
        ws.send_json(start_message("forged-token"))
        closing = ws.receive()
    assert closing == {"type": "websocket.close", "code": 1008, "reason": ""}
    assert client.app.state.services.sessions == {}


def test_extra_stream_without_admission_is_refused(make_client, make_settings):
    client = make_client(make_settings(MAX_CONCURRENT_CALLS=1), stt=FakeSTT())
    token = admit(client)
    services = client.app.state.services
    with client.websocket_connect("/twilio/stream") as first:
        first.send_json(start_message(token))
        assert wait_until(lambda: services.admission.active_count == 1)
        # A second call cannot get a slot, so its stream has no valid token.
        assert "<Hangup" in post_voice(client, voice_params(call_sid="CA" + "9" * 32)).text
        with client.websocket_connect("/twilio/stream") as second:
            second.send_json(start_message("no-slot", call_sid="CA" + "9" * 32))
            assert second.receive()["code"] == 1008
        first.send_json(stop_message())
        assert first.receive()["type"] == "websocket.close"
    assert services.admission.active_count == 0


def test_unsupported_media_format_is_refused(make_client):
    client = make_client(stt=FakeSTT())
    token = admit(client)
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json(start_message(token, sampleRate=16000))
        assert ws.receive()["code"] == 1003
    assert client.app.state.services.admission.active_count == 0


def test_max_call_duration_ends_stream(make_client, make_settings, caplog):
    caplog.set_level(logging.INFO)
    client = make_client(make_settings(MAX_CALL_SECONDS=0.3), stt=FakeSTT())
    token = admit(client)
    started = time.monotonic()
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json(start_message(token))
        closing = ws.receive()  # server closes on its own
    assert closing["type"] == "websocket.close" and closing["code"] == 1000
    assert time.monotonic() - started < 3
    assert any("max_call_duration_reached" in r.getMessage() for r in caplog.records)
    assert client.app.state.services.sessions == {}


def test_no_start_message_times_out(make_client, monkeypatch):
    monkeypatch.setattr(stream_module, "START_TIMEOUT", 0.2)
    client = make_client(stt=FakeSTT())
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json({"event": "connected"})
        assert ws.receive()["code"] == 1008


def test_too_many_malformed_messages_close_stream(make_client, monkeypatch):
    monkeypatch.setattr(stream_module, "MAX_MALFORMED", 3)
    client = make_client(stt=FakeSTT())
    token = admit(client)
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json(start_message(token))
        for _ in range(4):
            ws.send_text("garbage")
        assert ws.receive()["type"] == "websocket.close"
    assert client.app.state.services.sessions == {}


def test_client_disconnect_cleans_up(make_client):
    client = make_client(stt=FakeSTT())
    services = client.app.state.services
    token = admit(client)
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json(start_message(token))
        for payload in tone_mulaw_frames(1.0):
            ws.send_json(media(payload))
        assert wait_until(lambda: CALL_SID in services.sessions)
    assert wait_until(lambda: services.sessions == {} and services.admission.active_count == 0)


def test_stt_failure_keeps_call_running(make_client, caplog):
    class BrokenSTT(FakeSTT):
        async def transcribe(self, audio, sample_rate, lang):
            raise ConnectionError("whisper down")

    client = make_client(stt=BrokenSTT())
    token = admit(client)
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json(start_message(token))
        for payload in tone_mulaw_frames(3.2):
            ws.send_json(media(payload))
        ws.send_json(stop_message())
        assert ws.receive()["code"] == 1000
    assert any("stt_failed" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps({"event": "start", "streamSid": STREAM_SID}),
        json.dumps({"event": "media", "streamSid": STREAM_SID, "media": {"payload": "x" * 20000}}),
        json.dumps([1, 2, 3]),
        "x" * 40000,
    ],
)
def test_malformed_before_start_does_not_crash(make_client, raw, monkeypatch):
    monkeypatch.setattr(stream_module, "START_TIMEOUT", 0.3)
    client = make_client(stt=FakeSTT())
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_text(raw)
        assert ws.receive()["code"] == 1008  # start timeout, not a server error
