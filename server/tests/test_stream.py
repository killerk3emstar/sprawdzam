import json
import logging
import time

import pytest

from app.calls import stream as stream_module
from tests.conftest import (
    CALL_SID,
    SCAM_TEXT,
    STREAM_SID,
    FakeSTT,
    RecordingActions,
    admit,
    drain_until_close,
    media,
    post_voice,
    speech_mulaw_frames,
    start_message,
    stop_message,
    tone_mulaw_frames,
    voice_params,
    wait_until,
)


def test_full_stream_flow_blocks_scam_with_malformed_messages(make_client, caplog):
    caplog.set_level(logging.INFO)
    stt = FakeSTT([SCAM_TEXT])
    inner = RecordingActions()
    client = make_client(stt=stt, inner_actions=inner)
    services = client.app.state.services
    token = admit(client)
    frames = speech_mulaw_frames((3.5, 3.5))  # two utterances -> two STT segments

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
        # Segment 1 -> first high reading, segment 2 -> sustained high risk + rule hit -> no
        # family password configured -> scam blocked -> the backend closes the stream.
        messages, closing = drain_until_close(ws)

    assert closing["code"] == 1000
    media_out = [m for m in messages if m["event"] == "media"]
    assert len(media_out) >= 50  # ringback while nobody answered (+ the blocked notice)
    assert len(stt.calls) == 2
    for size, rate, lang, dtype in stt.calls:
        assert rate == 16000 and lang == "pl" and str(dtype) == "float32"
        assert 3.5 <= size / 16000 <= 4.2  # one utterance incl. pre-roll / trailing pause
    # The app was told about the call.
    (incoming,) = client.control.of_type("incoming_call")
    assert incoming["callId"] == CALL_SID and incoming["caller"] == "+48 *** *** 001"
    # REST hang-up as a backup is dry-run by default: nothing reached the provider.
    assert inner.calls == []
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "scam_blocked" in log_text and "telephony_would_hang_up" in log_text
    assert log_text.count("stream_malformed_message") == 5
    assert services.sessions == {} and services.admission.active_count == 0
    assert services.hub.bridges == {}
    # Privacy: no transcript text and no DTMF digit in the logs.
    assert "komisarz" not in log_text and "kurierowi" not in log_text
    assert '"digit"' not in log_text


def test_invalid_token_is_refused(make_client):
    client = make_client(stt=FakeSTT())
    admit(client)
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json({"event": "connected"})
        ws.send_json(start_message("forged-token"))
        closing = ws.receive()
    assert closing == {"type": "websocket.close", "code": 1008, "reason": ""}
    assert client.app.state.services.sessions == {}
    assert client.control.of_type("incoming_call") == []


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
        assert drain_until_close(first)[1]["code"] == 1000
    assert services.admission.active_count == 0


def test_unsupported_media_format_is_refused(make_client):
    client = make_client(stt=FakeSTT())
    token = admit(client)
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json(start_message(token, sampleRate=16000))
        assert ws.receive()["code"] == 1003
    assert client.app.state.services.admission.active_count == 0


def test_app_gone_before_stream_start_ends_call(make_client, caplog):
    client = make_client(stt=FakeSTT())
    token = admit(client)
    client.app.state.services.hub.remove_control(client.control)  # app disconnected
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json(start_message(token))
        assert ws.receive()["code"] == 1000
    assert any('"reason": "no_app"' in r.getMessage() for r in caplog.records)
    assert client.app.state.services.admission.active_count == 0


def test_max_call_duration_ends_stream(make_client, make_settings, caplog):
    caplog.set_level(logging.INFO)
    client = make_client(make_settings(MAX_CALL_SECONDS=0.3), stt=FakeSTT())
    token = admit(client)
    started = time.monotonic()
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json(start_message(token))
        _, closing = drain_until_close(ws)  # server closes on its own
    assert closing["code"] == 1000
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
        drain_until_close(ws)
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
    assert services.hub.bridges == {}


def test_stt_failure_keeps_call_running(make_client, caplog):
    class BrokenSTT(FakeSTT):
        async def transcribe(self, audio, sample_rate, lang):
            raise ConnectionError("whisper down")

    client = make_client(stt=BrokenSTT())
    token = admit(client)
    with client.websocket_connect("/twilio/stream") as ws:
        ws.send_json(start_message(token))
        for payload in speech_mulaw_frames((3.5,)):
            ws.send_json(media(payload))
        ws.send_json(stop_message())
        assert drain_until_close(ws)[1]["code"] == 1000
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
