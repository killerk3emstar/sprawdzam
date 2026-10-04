"""Protocol v0 `settings` from the senior app: validation, language, whitelist, trusted person."""

import logging
import xml.etree.ElementTree as ET

import pytest

from app.relay.device import DeviceSettings, choose_trusted_number
from app.relay.protocol import MAX_WHITELIST, SettingsMessage
from tests.conftest import (
    CALL_SID,
    DEVICE_TOKEN,
    SCAM_TEXT,
    FakeSTT,
    RecordingActions,
    admit,
    drain_until_close,
    media,
    post_voice,
    receive_json,
    scam_model,
    speech_mulaw_frames,
    start_message,
    stop_message,
    tone_mulaw_frames,
    voice_params,
    wait_until,
)

CALLER = "+48500000001"  # voice_params() default From
TRUSTED = "+48600000001"


def settings_message(**overrides) -> dict:
    message = {
        "type": "settings",
        "lang": "en",
        "trustedPerson": {"name": "Anna Kowalska", "number": "+48 600 000 001"},
        "whitelist": [CALLER, "+48700000002", "not-a-number", "+48 700 000 003"],
    }
    message.update(overrides)
    return message


def send_settings(client, message: dict) -> dict:
    with client.websocket_connect(f"/app/control?device_token={DEVICE_TOKEN}") as control:
        control.receive_json()  # protection_status
        control.send_json(message)
        return receive_json(control, "settings_ack")


def test_settings_are_validated_and_acknowledged(make_client, caplog):
    caplog.set_level(logging.INFO)
    client = make_client(app_online=False)
    ack = send_settings(client, settings_message())
    assert ack == {"type": "settings_ack", "accepted": True, "whitelist": 3, "ignored": 1}
    settings = client.app.state.services.hub.device_settings
    assert settings.lang == "en" and settings.trusted_number == TRUSTED
    assert settings.whitelist == {CALLER, "+48700000002", "+48700000003"}
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "app_settings_applied" in log_text
    for secret in (CALLER, TRUSTED, "Anna", "700000002"):
        assert secret not in log_text


@pytest.mark.parametrize(
    "overrides",
    [
        {"lang": "de"},
        {"trustedPerson": {"name": "X", "number": "600000001"}},
        {"whitelist": ["+48600000001"] * (MAX_WHITELIST + 1)},
        {"whitelist": "+48600000001"},
    ],
)
def test_invalid_settings_are_rejected(make_client, overrides):
    client = make_client(app_online=False)
    ack = send_settings(client, settings_message(**overrides))
    assert ack["accepted"] is False and ack["error"]
    assert client.app.state.services.hub.device_settings is None


def test_settings_language_applies_to_next_calls(make_client):
    client = make_client(app_online=False)
    with client.websocket_connect(f"/app/control?device_token={DEVICE_TOKEN}") as control:
        control.receive_json()
        control.send_json(settings_message(whitelist=[]))
        receive_json(control, "settings_ack")
        root = ET.fromstring(post_voice(client, voice_params()).text)
        assert root.find("Say").get("language") == "en-US"
        params = {p.get("name"): p.get("value") for p in root.findall("Connect/Stream/Parameter")}
        assert params["lang"] == "en"


def test_whitelisted_caller_is_bridged_without_analysis(make_client):
    stt = FakeSTT([SCAM_TEXT])
    client = make_client(stt=stt)
    hub = client.app.state.services.hub
    hub.apply_settings(DeviceSettings.from_message(SettingsMessage(**settings_message())))
    root = ET.fromstring(post_voice(client, voice_params()).text)
    assert root.find("Say") is None  # no protection notice for a contact
    with client.websocket_connect("/twilio/stream") as stream:
        stream.send_json(
            start_message(admit(client, call_sid="CA" + "4" * 32), call_sid="CA" + "4" * 32)
        )
        assert wait_until(lambda: client.control.of_type("incoming_call"))
        incoming = client.control.of_type("incoming_call")[-1]
        assert incoming["trusted"] is True and incoming["lang"] == "en"
        url = f"/app/call/{incoming['callId']}?token={incoming['token']}"
        with client.websocket_connect(url) as app_ws:
            app_ws.send_json({"type": "accept"})
            for payload in speech_mulaw_frames() + tone_mulaw_frames(1.0):
                stream.send_json(media(payload))
            frames = 0
            while frames < 20:  # the caller's audio still reaches the senior
                message = app_ws.receive()
                frames += message.get("bytes") is not None
            stream.send_json(stop_message())
            assert receive_json(app_ws, "call_ended")["reason"] == "caller_hangup"
        drain_until_close(stream)
    assert stt.calls == []  # never transcribed, never scored


def test_unknown_caller_is_still_analysed_with_settings(make_client):
    client = make_client(stt=FakeSTT([""]))
    client.app.state.services.hub.apply_settings(
        DeviceSettings.from_message(SettingsMessage(**settings_message(whitelist=[])))
    )
    with client.websocket_connect("/twilio/stream") as stream:
        stream.send_json(start_message(admit(client)))
        assert wait_until(lambda: client.control.of_type("incoming_call"))
        assert client.control.of_type("incoming_call")[-1]["trusted"] is False
        stream.send_json(stop_message())
        drain_until_close(stream)


def test_choose_trusted_number(caplog):
    device = DeviceSettings(lang="pl", trusted_number=TRUSTED)
    assert choose_trusted_number(device, "+48600000009", frozenset({TRUSTED})) == TRUSTED
    assert choose_trusted_number(device, "+48600000009", frozenset()) == "+48600000009"
    assert any("trusted_person_not_allowlisted" in r.getMessage() for r in caplog.records)
    assert choose_trusted_number(None, "+48600000009", frozenset()) == "+48600000009"
    assert TRUSTED not in "\n".join(r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(("allowlist", "expected"), [(TRUSTED, TRUSTED), ("", None)])
def test_app_trusted_person_needs_the_allowlist(make_client, make_settings, allowlist, expected):
    inner = RecordingActions()
    settings = make_settings(TELEPHONY_DRY_RUN=False, OUTBOUND_ALLOWLIST=allowlist)
    client = make_client(
        settings, stt=FakeSTT([SCAM_TEXT]), inner_actions=inner, decision_backend=scam_model()
    )
    client.app.state.services.hub.apply_settings(
        DeviceSettings.from_message(SettingsMessage(**settings_message(lang="pl", whitelist=[])))
    )
    with client.websocket_connect("/twilio/stream") as stream:
        stream.send_json(start_message(admit(client)))
        for payload in speech_mulaw_frames():
            stream.send_json(media(payload))
        drain_until_close(stream)  # blocked: no family password configured
    calls = [entry for entry in inner.calls if entry[0] in ("call", "sms")]
    if expected:
        assert {entry[2] for entry in calls} == {expected}
    else:
        assert calls == []  # not allowlisted and no TRUSTED_PERSON_NUMBER: nobody is called
    assert CALL_SID in {entry[1] for entry in inner.calls}
