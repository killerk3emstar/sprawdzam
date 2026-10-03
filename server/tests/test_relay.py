"""App relay (protocol v0): control channel, call channel, bridging, risk events."""

import base64
import logging
import time

import numpy as np
import pytest

from app.audio.g711 import mulaw_decode
from app.logging_setup import RedactTokensFilter, redact_tokens
from app.relay import protocol
from tests.conftest import (
    CALL_SID,
    DEVICE_TOKEN,
    SCAM_TEXT,
    FakeSTT,
    admit,
    drain_until_close,
    media,
    post_voice,
    receive_json,
    start_message,
    stop_message,
    tone_mulaw_frames,
    voice_params,
    wait_until,
)


def peak_hz(samples: np.ndarray, rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    return float(np.argmax(spectrum) * rate / len(samples))


def pcm16_tone(freq: float, seconds: float, rate: int = 16000) -> list[bytes]:
    t = np.arange(int(seconds * rate)) / rate
    pcm = (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2").tobytes()
    return [pcm[i : i + 640] for i in range(0, len(pcm), 640)]


def start_call(client, stream_ws) -> dict:
    """Webhook + stream start; returns the incoming_call the app received."""
    stream_ws.send_json(start_message(admit(client)))
    assert wait_until(lambda: client.control.of_type("incoming_call"))
    return client.control.of_type("incoming_call")[-1]


def call_url(incoming: dict) -> str:
    return f"/app/call/{incoming['callId']}?token={incoming['token']}"


def until_event(ws, event: str, limit: int = 5000) -> list[dict]:
    """Read provider-stream messages until `event` (inclusive)."""
    seen = []
    for _ in range(limit):
        message = receive_json(ws)
        seen.append(message)
        if message.get("event") == event:
            return seen
    raise AssertionError(f"no {event}")


# ---------------------------------------------------------------------- control channel
@pytest.mark.parametrize("query", ["", "?device_token=wrong-token-0123456789", "?device_token="])
def test_control_rejects_bad_device_token(make_client, query, caplog):
    client = make_client(app_online=False)
    with client.websocket_connect(f"/app/control{query}") as ws:
        assert ws.receive()["code"] == protocol.CLOSE_POLICY
    assert any("app_control_rejected" in r.getMessage() for r in caplog.records)
    assert not client.app.state.services.hub.online


def test_control_rejects_everything_without_configured_token(make_client, make_settings):
    client = make_client(make_settings(APP_DEVICE_TOKEN=""), app_online=False)
    with client.websocket_connect(f"/app/control?device_token={DEVICE_TOKEN}") as ws:
        assert ws.receive()["code"] == protocol.CLOSE_POLICY


def test_control_status_ping_pong_and_online(make_client):
    client = make_client(app_online=False)
    hub = client.app.state.services.hub
    with client.websocket_connect(f"/app/control?device_token={DEVICE_TOKEN}") as ws:
        assert ws.receive_json() == {"type": "protection_status", "available": True}
        assert hub.online
        ws.send_text("{not json")  # ignored
        ws.send_json({"type": "future_feature"})  # unknown type: ignored
        ws.send_bytes(b"\x00")  # ignored
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        # With the real app connected the webhook connects the call.
        assert "<Connect>" in post_voice(client, voice_params()).text
    assert wait_until(lambda: not hub.online)
    assert "<Hangup" in post_voice(client, voice_params(call_sid="CA" + "3" * 32)).text


def test_control_idle_timeout(make_client, monkeypatch):
    monkeypatch.setattr(protocol, "CONTROL_IDLE_TIMEOUT_SECONDS", 0.2)
    client = make_client(app_online=False)
    with client.websocket_connect(f"/app/control?device_token={DEVICE_TOKEN}") as ws:
        assert ws.receive_json()["type"] == "protection_status"
        assert ws.receive()["code"] == protocol.CLOSE_IDLE


def test_incoming_call_reaches_real_control_channel(make_client):
    client = make_client(app_online=False, stt=FakeSTT())
    with client.websocket_connect(f"/app/control?device_token={DEVICE_TOKEN}") as control:
        control.receive_json()
        token = admit(client)
        with client.websocket_connect("/twilio/stream") as stream:
            stream.send_json(start_message(token))
            incoming = control.receive_json()
            assert incoming == {
                "type": "incoming_call",
                "callId": CALL_SID,
                "token": incoming["token"],
                "caller": "+48 *** *** 001",
                "lang": "pl",
            }
            assert len(incoming["token"]) >= 32
            stream.send_json(stop_message())
            drain_until_close(stream)


# ---------------------------------------------------------------------- call tokens
def test_call_token_is_single_use_and_bound_to_call(make_client):
    client = make_client(stt=FakeSTT())
    with client.websocket_connect("/twilio/stream") as stream:
        incoming = start_call(client, stream)
        with client.websocket_connect(f"/app/call/{CALL_SID}?token=forged") as bad:
            assert bad.receive()["code"] == protocol.CLOSE_POLICY
        with client.websocket_connect(f"/app/call/bad%20id?token={incoming['token']}") as bad:
            assert bad.receive()["code"] == protocol.CLOSE_POLICY
        with client.websocket_connect(call_url(incoming)) as app_ws:
            with client.websocket_connect(call_url(incoming)) as reuse:
                assert reuse.receive()["code"] == protocol.CLOSE_POLICY
            app_ws.send_json({"type": "accept"})
            until_event(stream, "clear")  # the first connection works
            stream.send_json(stop_message())
            assert receive_json(app_ws, "call_ended") == {
                "type": "call_ended",
                "reason": "caller_hangup",
            }
        drain_until_close(stream)


def test_expired_call_token_is_rejected(make_client, monkeypatch):
    monkeypatch.setattr(protocol, "CALL_TOKEN_TTL_SECONDS", 0.05)
    client = make_client(stt=FakeSTT())
    with client.websocket_connect("/twilio/stream") as stream:
        incoming = start_call(client, stream)
        time.sleep(0.1)
        with client.websocket_connect(call_url(incoming)) as app_ws:
            assert app_ws.receive()["code"] == protocol.CLOSE_POLICY
        stream.send_json(stop_message())
        drain_until_close(stream)


# ---------------------------------------------------------------------- bridging
def test_audio_is_bridged_both_ways_with_format_conversion(make_client):
    client = make_client(stt=FakeSTT())
    hub = client.app.state.services.hub
    with client.websocket_connect("/twilio/stream") as stream:
        incoming = start_call(client, stream)
        with client.websocket_connect(call_url(incoming)) as app_ws:
            # Senior audio before accept is not forwarded.
            app_ws.send_bytes(pcm16_tone(500, 0.1)[0])
            assert wait_until(lambda: hub.bridges[CALL_SID].app is not None)
            assert hub.bridges[CALL_SID].stats["to_phone_frames"] == 0
            app_ws.send_json({"type": "accept"})
            ringing = until_event(stream, "clear")
            assert ringing[0]["event"] == "media"  # ringback before the answer

            # Caller -> app: mu-law 8 kHz in, PCM16 LE 16 kHz 640-byte frames out.
            for payload in tone_mulaw_frames(1.0, freq=1000):
                stream.send_json(media(payload))
            frames = []
            while len(frames) < 30:
                message = app_ws.receive()
                if message.get("bytes") is not None:
                    frames.append(message["bytes"])
            assert all(len(f) == 640 for f in frames)
            caller_audio = np.frombuffer(b"".join(frames[5:]), dtype="<i2") / 32768
            assert abs(peak_hz(caller_audio, 16000) - 1000) < 20

            # App -> caller: PCM16 16 kHz in, mu-law 8 kHz `media` (160-byte frames) out.
            app_ws.send_bytes(b"\x00\x01\x02")  # odd size: dropped, no crash
            for frame in pcm16_tone(500, 1.0):
                app_ws.send_bytes(frame)
            payloads = []
            while len(payloads) < 30:
                message = receive_json(stream)
                if message["event"] == "media":
                    payloads.append(base64.b64decode(message["media"]["payload"]))
            assert all(len(p) == 160 for p in payloads)
            senior_audio = mulaw_decode(b"".join(payloads[5:])) / 32768
            assert abs(peak_hz(senior_audio, 8000) - 500) < 20

            stream.send_json(stop_message())
            assert receive_json(app_ws, "call_ended")["reason"] == "caller_hangup"
        drain_until_close(stream)
    assert hub.bridges == {}


def test_accept_timeout_ends_call(make_client, make_settings):
    client = make_client(make_settings(APP_ACCEPT_TIMEOUT_SECONDS=0.3), stt=FakeSTT())
    with client.websocket_connect("/twilio/stream") as stream:
        incoming = start_call(client, stream)
        with client.websocket_connect(call_url(incoming)) as app_ws:
            messages, closing = drain_until_close(app_ws)
        assert {"type": "call_ended", "reason": "timeout"} in messages
        assert closing["code"] == 1000
        assert drain_until_close(stream)[1]["code"] == 1000  # provider call ends


def test_senior_hangup_ends_call(make_client):
    client = make_client(stt=FakeSTT())
    with client.websocket_connect("/twilio/stream") as stream:
        incoming = start_call(client, stream)
        with client.websocket_connect(call_url(incoming)) as app_ws:
            app_ws.send_json({"type": "accept"})
            app_ws.send_json({"type": "hangup"})
            messages, _ = drain_until_close(app_ws)
        assert {"type": "call_ended", "reason": "senior_hangup"} in messages
        assert drain_until_close(stream)[1]["code"] == 1000


def test_app_channel_drop_ends_call(make_client, caplog):
    client = make_client(stt=FakeSTT())
    with client.websocket_connect("/twilio/stream") as stream:
        incoming = start_call(client, stream)
        with client.websocket_connect(call_url(incoming)) as app_ws:
            app_ws.send_json({"type": "accept"})
            until_event(stream, "clear")
        assert drain_until_close(stream)[1]["code"] == 1000
    assert any("app_call_channel_dropped" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------- risk events
def test_risk_events_and_scam_block_reach_the_app(make_client):
    client = make_client(stt=FakeSTT([SCAM_TEXT]))
    with client.websocket_connect("/twilio/stream") as stream:
        incoming = start_call(client, stream)
        with client.websocket_connect(call_url(incoming)) as app_ws:
            app_ws.send_json({"type": "accept"})
            for payload in tone_mulaw_frames(6.5):
                stream.send_json(media(payload))
            messages, closing = drain_until_close(app_ws)
        events = [m for m in messages if isinstance(m, dict)]
        risks = [e for e in events if e["type"] == "risk"]
        assert [r["level"] for r in risks] == ["warn", "high"]
        assert risks[0]["score"] >= 50 and risks[0]["scamType"] == "police"
        assert {"money", "secrecy", "authority"} <= set(risks[1]["reasons"])
        assert [e["type"] for e in events][-2:] == ["verify_password", "call_ended"]
        assert events[-1]["reason"] == "scam_blocked"
        assert sum(isinstance(m, bytes) for m in messages) >= 25  # caller audio + warning tone
        assert closing["code"] == 1000
        assert drain_until_close(stream)[1]["code"] == 1000


@pytest.mark.parametrize("source", ["app", "caller"])
def test_family_password_lets_the_call_continue(make_client, make_settings, source, caplog):
    caplog.set_level(logging.INFO)
    settings = make_settings(FAMILY_PASSWORD="2468", VERIFY_PASSWORD_SECONDS=5)
    client = make_client(settings, stt=FakeSTT([SCAM_TEXT]))
    with client.websocket_connect("/twilio/stream") as stream:
        incoming = start_call(client, stream)
        with client.websocket_connect(call_url(incoming)) as app_ws:
            app_ws.send_json({"type": "accept"})
            for payload in tone_mulaw_frames(6.5):
                stream.send_json(media(payload))
            receive_json(app_ws, "verify_password")
            if source == "app":
                app_ws.send_json({"type": "dtmf", "digits": "2468"})
            else:
                for digit in "92468":  # a wrong leading digit is fine (suffix match)
                    stream.send_json(
                        {
                            "event": "dtmf",
                            "streamSid": start_message("")["streamSid"],
                            "dtmf": {"digit": digit},
                        }
                    )
            assert wait_until(
                lambda: any(
                    "incident_cleared_by_password" in r.getMessage() for r in caplog.records
                )
            )
            stream.send_json(stop_message())
            assert receive_json(app_ws, "call_ended")["reason"] == "caller_hangup"
        drain_until_close(stream)
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "2468" not in log_text and "scam_blocked" not in log_text


def test_wrong_password_blocks(make_client, make_settings):
    settings = make_settings(FAMILY_PASSWORD="2468", VERIFY_PASSWORD_SECONDS=0.5)
    client = make_client(settings, stt=FakeSTT([SCAM_TEXT]))
    with client.websocket_connect("/twilio/stream") as stream:
        incoming = start_call(client, stream)
        with client.websocket_connect(call_url(incoming)) as app_ws:
            app_ws.send_json({"type": "accept"})
            for payload in tone_mulaw_frames(6.5):
                stream.send_json(media(payload))
            receive_json(app_ws, "verify_password")
            app_ws.send_json({"type": "dtmf", "digits": "1111"})
            assert receive_json(app_ws, "call_ended")["reason"] == "scam_blocked"
        drain_until_close(stream)


# ---------------------------------------------------------------------- logging
def test_tokens_are_redacted_from_access_logs():
    assert redact_tokens("/app/control?device_token=abc123&x=1") == (
        "/app/control?device_token=***&x=1"
    )
    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:5000", "/app/call/CA1?token=SECRET123"),
        None,
    )
    RedactTokensFilter().filter(record)
    assert "SECRET123" not in record.getMessage()
    assert "token=***" in record.getMessage()
