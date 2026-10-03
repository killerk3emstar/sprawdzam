import xml.etree.ElementTree as ET

from tests.conftest import (
    AUTH_TOKEN,
    BASE_URL,
    CALL_SID,
    post_voice,
    twilio_signature,
    voice_params,
)


def test_valid_signature_returns_connect_stream_twiml(make_client):
    client = make_client()
    response = post_voice(client, voice_params())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    body = response.text
    assert "<Connect><Stream" in body
    root = ET.fromstring(body)
    say = root.find("Say")
    assert say is not None and say.get("language") == "pl-PL"
    assert "chronione przez usługę Sprawdzam" in say.text
    stream = root.find("Connect/Stream")
    assert stream.get("url") == "wss://sprawdzam.example.test/twilio/stream"
    params = {p.get("name"): p.get("value") for p in stream.findall("Parameter")}
    assert params["lang"] == "pl"
    assert params["callId"] == CALL_SID
    assert len(params["token"]) >= 32


def test_english_notice(make_client, make_settings):
    client = make_client(make_settings(DEFAULT_LANG="en"))
    root = ET.fromstring(post_voice(client, voice_params()).text)
    assert root.find("Say").get("language") == "en-US"
    assert "protected by the Second Ear service" in root.find("Say").text


def test_invalid_signature_is_rejected(make_client):
    client = make_client()
    response = post_voice(client, voice_params(), signature="bm90LWEtdmFsaWQtc2lnbmF0dXJl")
    assert response.status_code == 403


def test_missing_signature_is_rejected(make_client):
    assert post_voice(make_client(), voice_params(), signature=None).status_code == 403


def test_tampered_params_are_rejected(make_client):
    client = make_client()
    params = voice_params()
    signature = twilio_signature(f"{BASE_URL}/twilio/voice", params)
    params["From"] = "+48999999999"
    response = post_voice(client, params, signature=signature)
    assert response.status_code == 403


def test_signature_uses_public_base_url_not_request_host(make_client):
    # The TestClient talks to http://testserver; the signature is over PUBLIC_BASE_URL.
    client = make_client()
    params = voice_params()
    wrong = twilio_signature("http://testserver/twilio/voice", params)
    assert post_voice(client, params, signature=wrong).status_code == 403


def test_no_auth_token_refuses_webhooks(make_client, make_settings):
    client = make_client(make_settings(TWILIO_AUTH_TOKEN=""))
    assert post_voice(client, voice_params(), signature=None).status_code == 403


def test_dev_flag_allows_unsigned_webhooks(make_client, make_settings, caplog):
    client = make_client(make_settings(TWILIO_AUTH_TOKEN="", ALLOW_UNSIGNED_WEBHOOKS=True))
    response = post_voice(client, voice_params(), signature=None)
    assert response.status_code == 200
    assert "<Connect><Stream" in response.text
    assert any("twilio_signature_skipped" in r.getMessage() for r in caplog.records)


def test_dev_flag_ignored_when_token_is_set(make_client, make_settings):
    client = make_client(make_settings(ALLOW_UNSIGNED_WEBHOOKS=True))
    assert post_voice(client, voice_params(), signature=None).status_code == 403


def test_wrong_content_type(make_client):
    client = make_client()
    response = client.post("/twilio/voice", json=voice_params())
    assert response.status_code == 415


def test_body_too_large(make_client):
    client = make_client()
    params = voice_params(Junk="x" * 20_000)
    assert post_voice(client, params).status_code == 413


def test_invalid_call_sid(make_client):
    client = make_client()
    assert post_voice(client, voice_params(call_sid="CA-not-valid")).status_code == 400


def test_account_mismatch(make_client):
    client = make_client()
    params = voice_params(AccountSid="AC" + "b" * 32)
    assert post_voice(client, params).status_code == 403


def test_rate_limit_returns_429(make_client, make_settings):
    client = make_client(make_settings(MAX_INCOMING_CALLS_PER_MINUTE=2, MAX_CONCURRENT_CALLS=10))
    codes = [post_voice(client, voice_params(call_sid=f"CA{i:032x}")).status_code for i in range(3)]
    assert codes == [200, 200, 429]


def test_concurrency_limit_plays_unavailable_and_hangs_up(make_client, make_settings):
    client = make_client(make_settings(MAX_CONCURRENT_CALLS=1))
    first = post_voice(client, voice_params(call_sid="CA" + "1" * 32))
    second = post_voice(client, voice_params(call_sid="CA" + "2" * 32))
    assert "<Connect>" in first.text
    assert second.status_code == 200
    root = ET.fromstring(second.text)
    assert root.find("Hangup") is not None
    assert root.find("Connect") is None
    assert "chwilowo niedostępna" in root.find("Say").text


def test_health_reports_configuration_without_secrets(make_client, make_settings):
    settings = make_settings(
        OUTBOUND_ALLOWLIST="+48600000001", TRUSTED_PERSON_NUMBER="+48600000001"
    )
    client = make_client(settings)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["twilio"]["signature_validation"] == "enforced"
    assert data["protection"] == "rules_only"
    assert data["limits"]["dry_run"] is True
    assert data["limits"]["allowlist_size"] == 1
    assert data["limits"]["max_concurrent_calls"] == 2
    text = response.text
    assert AUTH_TOKEN not in text
    assert "+48600000001" not in text
