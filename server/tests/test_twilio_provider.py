import base64
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs

import httpx
import pytest

from app.telephony.provider import (
    InvalidWebhook,
    MalformedStreamMessage,
    StreamConnected,
    StreamDtmf,
    StreamMark,
    StreamMedia,
    StreamStarted,
    StreamStopped,
    TelephonyProvider,
    WebhookAuth,
    WebhookForbidden,
)
from app.twilio.provider import TwilioProvider
from app.twilio.rest import ProviderNotConfigured
from tests.conftest import ACCOUNT_SID, AUTH_TOKEN, BASE_URL, twilio_signature

STREAM_SID = "MZ" + "0" * 32
CALL_SID = "CA" + "1" * 32

pytestmark = pytest.mark.anyio


@pytest.fixture
def provider(make_settings) -> TwilioProvider:
    return TwilioProvider(make_settings())


def test_implements_protocol(provider):
    assert isinstance(provider, TelephonyProvider)
    assert provider.name == "twilio"


# ---------------------------------------------------------------------- stream parsing
def test_parses_start(provider):
    event = provider.parse_stream_message(
        {
            "event": "start",
            "sequenceNumber": "1",
            "streamSid": STREAM_SID,
            "start": {
                "accountSid": ACCOUNT_SID,
                "streamSid": STREAM_SID,
                "callSid": CALL_SID,
                "tracks": ["inbound"],
                "customParameters": {"token": "t", "lang": "en"},
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
            },
        }
    )
    assert event == StreamStarted(
        STREAM_SID, CALL_SID, {"token": "t", "lang": "en"}, "audio/x-mulaw", 8000, 1
    )


def test_parses_media_and_normalises_track(provider):
    payload = base64.b64encode(b"\xff" * 160).decode()
    event = provider.parse_stream_message(
        {
            "event": "media",
            "streamSid": STREAM_SID,
            "media": {"track": "inbound_track", "payload": payload},
        }
    )
    assert event == StreamMedia(STREAM_SID, "inbound", b"\xff" * 160)


def test_parses_other_events(provider):
    assert provider.parse_stream_message({"event": "connected"}) == StreamConnected()
    assert provider.parse_stream_message(
        {"event": "mark", "streamSid": STREAM_SID, "mark": {"name": "w"}}
    ) == StreamMark(STREAM_SID, "w")
    assert provider.parse_stream_message(
        {"event": "dtmf", "streamSid": STREAM_SID, "dtmf": {"digit": "7"}}
    ) == StreamDtmf(STREAM_SID, "7")
    assert provider.parse_stream_message(
        {"event": "stop", "streamSid": STREAM_SID}
    ) == StreamStopped(STREAM_SID)


def test_unknown_event_is_skipped(provider):
    assert provider.parse_stream_message({"event": "something_new"}) is None


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        ({"event": "media", "streamSid": STREAM_SID}, "schema"),
        ({"event": "media", "streamSid": "short", "media": {"payload": ""}}, "schema"),
        ({"event": "start", "streamSid": STREAM_SID, "start": {"callSid": "x"}}, "schema"),
        ({"event": "dtmf", "streamSid": STREAM_SID, "dtmf": {"digit": "55"}}, "schema"),
        ({"event": "media", "streamSid": STREAM_SID, "media": {"payload": "A" * 20_000}}, "schema"),
        (
            {"event": "media", "streamSid": STREAM_SID, "media": {"payload": "@@@"}},
            "invalid_base64",
        ),
        (
            {
                "event": "start",
                "streamSid": STREAM_SID,
                "start": {"streamSid": "MZ" + "9" * 32, "callSid": CALL_SID},
            },
            "stream_sid_mismatch",
        ),
        ([1, 2, 3], "schema"),
    ],
)
def test_rejects_malformed_messages(provider, data, reason):
    with pytest.raises(MalformedStreamMessage) as info:
        provider.parse_stream_message(data)
    assert info.value.reason == reason


def test_malformed_errors_never_contain_input(provider):
    with pytest.raises(MalformedStreamMessage) as info:
        provider.parse_stream_message(
            {"event": "media", "streamSid": STREAM_SID, "media": {"payload": 12345}}
        )
    assert "12345" not in str(info.value.errors)


def test_outbound_builders(provider):
    assert provider.media_message(STREAM_SID, b"\x00\xff") == {
        "event": "media",
        "streamSid": STREAM_SID,
        "media": {"payload": "AP8="},
    }
    assert provider.mark_message(STREAM_SID, "w1") == {
        "event": "mark",
        "streamSid": STREAM_SID,
        "mark": {"name": "w1"},
    }
    assert provider.clear_message(STREAM_SID) == {"event": "clear", "streamSid": STREAM_SID}


# ---------------------------------------------------------------------- webhooks
def test_markup(provider):
    root = ET.fromstring(provider.connect_markup("wss://x/twilio/stream", "en", CALL_SID, "tok"))
    assert root.find("Say").get("voice") == "Polly.Joanna"
    assert root.find("Connect/Stream").get("url") == "wss://x/twilio/stream"
    root = ET.fromstring(provider.unavailable_markup("pl"))
    assert root.find("Hangup") is not None
    assert "chwilowo niedostępna" in root.find("Say").text


def test_verify_webhook(provider):
    params = {"CallSid": CALL_SID}
    signature = twilio_signature(f"{BASE_URL}/twilio/voice", params)
    headers = {"x-twilio-signature": signature}
    assert provider.verify_webhook("/twilio/voice", "", params, headers) is WebhookAuth.VALID
    assert provider.verify_webhook("/other", "", params, headers) is WebhookAuth.INVALID
    assert provider.verify_webhook("/twilio/voice", "", params, {}) is WebhookAuth.MISSING


def test_parse_incoming_call(provider):
    call = provider.parse_incoming_call(
        {"CallSid": CALL_SID, "AccountSid": ACCOUNT_SID, "From": "+48500000001"}
    )
    assert (call.call_id, call.caller) == (CALL_SID, "+48500000001")
    with pytest.raises(WebhookForbidden):
        provider.parse_incoming_call({"CallSid": CALL_SID, "AccountSid": "AC" + "b" * 32})
    with pytest.raises(InvalidWebhook):
        provider.parse_incoming_call({"CallSid": "nope"})


# ---------------------------------------------------------------------- REST
class Recorder:
    def __init__(self, status: int = 201) -> None:
        self.requests: list[httpx.Request] = []
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json={"sid": "XX"})


def rest_provider(make_settings, recorder, **overrides):
    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    return TwilioProvider(make_settings(**overrides), http_client=client)


async def test_rest_hang_up(make_settings):
    recorder = Recorder()
    provider = rest_provider(make_settings, recorder)
    await provider.hang_up(CALL_SID)
    request = recorder.requests[0]
    assert request.method == "POST"
    assert str(request.url) == (
        f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Calls/{CALL_SID}.json"
    )
    expected = "Basic " + base64.b64encode(f"{ACCOUNT_SID}:{AUTH_TOKEN}".encode()).decode()
    assert request.headers["authorization"] == expected
    assert parse_qs(request.content.decode()) == {"Status": ["completed"]}


async def test_rest_call_and_sms_use_api_key_when_set(make_settings):
    recorder = Recorder()
    provider = rest_provider(
        make_settings, recorder, TWILIO_API_KEY_SID="SK" + "1" * 32, TWILIO_API_KEY_SECRET="s3"
    )
    await provider.call_trusted_person(CALL_SID, "+48600000001", "Uwaga", "pl")
    await provider.send_sms(CALL_SID, "+48600000001", "Alert")
    call, sms = (parse_qs(r.content.decode()) for r in recorder.requests)
    assert call["To"] == ["+48600000001"] and call["From"] == ["+48100000000"]
    assert "<Say" in call["Twiml"][0] and "Uwaga" in call["Twiml"][0]
    assert sms == {"To": ["+48600000001"], "From": ["+48100000000"], "Body": ["Alert"]}
    expected = "Basic " + base64.b64encode(("SK" + "1" * 32 + ":s3").encode()).decode()
    assert recorder.requests[0].headers["authorization"] == expected


async def test_rest_errors(make_settings):
    provider = rest_provider(make_settings, Recorder(status=500))
    with pytest.raises(httpx.HTTPStatusError):
        await provider.send_sms(CALL_SID, "+48600000001", "x")
    with pytest.raises(ValueError):
        await provider.hang_up("CA../../evil")
    unconfigured = rest_provider(make_settings, Recorder(), TWILIO_AUTH_TOKEN="")
    with pytest.raises(ProviderNotConfigured):
        await unconfigured.hang_up(CALL_SID)
    no_number = rest_provider(make_settings, Recorder(), TWILIO_NUMBER="")
    with pytest.raises(ProviderNotConfigured):
        await no_number.send_sms(CALL_SID, "+48600000001", "x")
