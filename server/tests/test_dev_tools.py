import re

import pytest

from tests.conftest import FakeSTT, drain_until_close, start_message, stop_message, wait_until

DEV_PATHS = ["/dev/caller", "/dev/senior", "/dev/static/audio.js", "/dev/static/pcm-worklet.js"]


@pytest.mark.parametrize("path", DEV_PATHS)
def test_dev_routes_absent_by_default(make_client, path):
    client = make_client()
    assert client.get(path).status_code == 404
    assert client.post("/dev/calls", json={}).status_code in (404, 405)


@pytest.mark.parametrize("path", DEV_PATHS + ["/dev/static/style.css"])
def test_dev_pages_served_when_enabled(make_client, make_settings, path):
    client = make_client(make_settings(DEV_TOOLS=True))
    response = client.get(path)
    assert response.status_code == 200
    # Self-contained: no third-party scripts, styles or fonts.
    assert not re.search(r"(src|href)=\"https?://", response.text)


def test_dev_call_uses_the_real_stream_path(make_client, make_settings):
    client = make_client(make_settings(DEV_TOOLS=True), stt=FakeSTT())
    response = client.post("/dev/calls", json={"caller": "+48600123456", "lang": "en"})
    assert response.status_code == 200
    data = response.json()
    assert re.fullmatch(r"CA[0-9a-f]{32}", data["callId"])
    assert data["streamPath"] == "/twilio/stream" and data["lang"] == "en"
    assert "Second Ear" in data["notice"]
    with client.websocket_connect(data["streamPath"]) as stream:
        stream.send_json(start_message(data["token"], call_sid=data["callId"]))
        assert wait_until(lambda: client.control.of_type("incoming_call"))
        incoming = client.control.of_type("incoming_call")[0]
        assert incoming["caller"] == "+48 *** *** 456" and incoming["lang"] == "en"
        stream.send_json(stop_message())
        drain_until_close(stream)


def test_dev_call_without_app_is_unavailable(make_client, make_settings):
    client = make_client(make_settings(DEV_TOOLS=True), app_online=False)
    response = client.post("/dev/calls", json={})
    assert response.status_code == 503
    assert response.json()["reason"] == "no_app"
    assert "chwilowo niedostępna" in response.json()["message"]


def test_dev_call_validation_and_rate_limit(make_client, make_settings):
    client = make_client(
        make_settings(DEV_TOOLS=True, MAX_INCOMING_CALLS_PER_MINUTE=1, MAX_CONCURRENT_CALLS=5)
    )
    assert client.post("/dev/calls", json={"caller": "not-a-number"}).status_code == 422
    assert client.post("/dev/calls", json={"lang": "de"}).status_code == 422
    assert client.post("/dev/calls", json={}).status_code == 200
    assert client.post("/dev/calls", json={}).status_code == 429
