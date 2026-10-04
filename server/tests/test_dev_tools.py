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


def test_samples_are_listed_and_served(make_client, make_settings, tmp_path):
    samples = tmp_path / "data" / "samples"
    samples.mkdir(parents=True)
    (samples / "pl_scam_police.ulaw").write_bytes(b"\xff" * 16000)
    (samples / "en_normal_family.ulaw").write_bytes(b"\x7f" * 8000)
    (samples / "Bad Name.ulaw").write_bytes(b"\xff" * 10)
    (samples / "pl_empty.ulaw").write_bytes(b"")
    client = make_client(make_settings(DEV_TOOLS=True))
    listing = client.get("/dev/samples").json()["samples"]
    assert listing == [
        {"name": "en_normal_family", "lang": "en", "seconds": 1.0},
        {"name": "pl_scam_police", "lang": "pl", "seconds": 2.0},
    ]
    response = client.get("/dev/samples/pl_scam_police.ulaw")
    assert response.status_code == 200 and response.content == b"\xff" * 16000
    assert response.headers["content-type"] == "audio/basic"
    for bad in ["../secrets", "pl_missing", "Bad%20Name", "xx_scam"]:
        assert client.get(f"/dev/samples/{bad}.ulaw").status_code == 404


def test_samples_listing_without_directory(make_client, make_settings):
    client = make_client(make_settings(DEV_TOOLS=True))
    assert client.get("/dev/samples").json() == {"samples": []}


def test_sample_routes_absent_by_default(make_client):
    client = make_client()
    assert client.get("/dev/samples").status_code == 404
    assert client.get("/dev/samples/pl_scam_police.ulaw").status_code == 404
