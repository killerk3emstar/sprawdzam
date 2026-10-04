"""Trusted-person alert sent by the senior's phone (protocol v0 extension)."""

import json

import pytest

from app.events import EventBus
from app.relay import protocol, trusted_alert
from app.relay.hub import TRUSTED_ALERT_TTL_SECONDS, AppHub
from app.relay.trusted_alert import compose_alert_text
from tests.conftest import (
    DEVICE_TOKEN,
    SCAM_TEXT,
    FakeControl,
    FakeSTT,
    admit,
    drain_until_close,
    media,
    receive_json,
    scam_model,
    speech_mulaw_frames,
    start_message,
    wait_until,
)


# ---------------------------------------------------------------------- text
def test_pl_text_matches_the_demo_wording():
    text = compose_alert_text("police", ["authority", "money", "secrecy"], "pl")
    assert text == (
        "Sprawdzam: babcia mogla rozmawiac z oszustem (falszywy policjant, prosba o gotowke). "
        "Zadzwon do niej."
    )


@pytest.mark.parametrize("lang", ["pl", "en"])
@pytest.mark.parametrize("scam", ["none", "grandchild", "police", "bank", "other", "weird"])
@pytest.mark.parametrize(
    "reasons", [[], ["money"], ["secrecy"], ["authority"], ["urgency"], ["urgency", "secrecy"]]
)
def test_texts_are_ascii_short_and_without_links(lang, scam, reasons):
    text = compose_alert_text(scam, reasons, lang)
    assert text.isascii() and len(text) < 160
    assert "http" not in text and "www" not in text
    if lang == "en":
        assert "babcia" not in text and text.startswith("Second Ear:")
    else:
        assert trusted_alert.SENIOR_PL in text


def test_generic_fallback_and_main_reason():
    assert compose_alert_text("none", [], "pl") == (
        "Sprawdzam: babcia mogla rozmawiac z oszustem. Zadzwon do niej."
    )
    assert "(asked to keep it secret)" in compose_alert_text("none", ["urgency", "secrecy"], "en")
    assert "(fake bank employee, asked for money)" in compose_alert_text("bank", ["money"], "en")


def test_senior_word_is_one_constant(monkeypatch):
    monkeypatch.setattr(trusted_alert, "SENIOR_PL", "mama")
    assert compose_alert_text("none", [], "pl").startswith("Sprawdzam: mama mogla")


# ---------------------------------------------------------------------- hub (unit)
class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def message(call_id: str = "CA1") -> dict:
    return protocol.alert_trusted(call_id, "police", ["money"], "pl", "text")


def hub_with_events(clock=None) -> tuple[AppHub, EventBus]:
    hub = AppHub(DEVICE_TOKEN, clock=clock or Clock())
    hub.events = EventBus()
    return hub, hub.events


def actions(bus: EventBus) -> list[str]:
    sub = bus.subscribe()
    seen = []
    while not sub.queue.empty():
        event = sub.queue.get_nowait()
        if event["type"] == "action":
            seen.append(event["action"])
    return seen


@pytest.mark.anyio
async def test_alert_is_sent_once_per_call():
    hub, _ = hub_with_events()
    control = FakeControl()
    hub.add_control(control)
    assert await hub.send_trusted_alert("CA1", message())
    assert not await hub.send_trusted_alert("CA1", message())  # retry: refused
    hub.remove_control(control)
    again = FakeControl()
    hub.add_control(again)
    assert await hub.deliver_pending_alerts(again) == 0  # reconnect: not resent
    assert len(control.of_type("alert_trusted")) == 1 and again.messages == []


@pytest.mark.anyio
async def test_alert_waits_for_the_app_and_is_delivered_on_reconnect():
    clock = Clock()
    hub, bus = hub_with_events(clock)
    sub = bus.subscribe()
    assert not await hub.send_trusted_alert("CA1", message())  # no app connected
    clock.now += TRUSTED_ALERT_TTL_SECONDS - 1
    control = FakeControl()
    assert await hub.deliver_pending_alerts(control) == 1
    assert control.of_type("alert_trusted")[0]["callId"] == "CA1"
    assert await hub.deliver_pending_alerts(FakeControl()) == 0  # only once
    events = [sub.queue.get_nowait() for _ in range(sub.queue.qsize())]
    assert [e["action"] for e in events if e["type"] == "action"] == ["sms_requested"]


@pytest.mark.anyio
async def test_queued_alert_expires_after_two_minutes():
    clock = Clock()
    hub, bus = hub_with_events(clock)
    sub = bus.subscribe()
    await hub.send_trusted_alert("CA1", message())
    clock.now += TRUSTED_ALERT_TTL_SECONDS
    control = FakeControl()
    assert await hub.deliver_pending_alerts(control) == 0
    assert control.messages == []
    events = [sub.queue.get_nowait() for _ in range(sub.queue.qsize())]
    action = [e for e in events if e["type"] == "action"][0]
    assert action["action"] == "sms_failed" and action["detail"] == "app_not_connected"


@pytest.mark.anyio
async def test_results_are_published_once_and_unknown_calls_ignored():
    hub, bus = hub_with_events()
    control = FakeControl()
    hub.add_control(control)
    sub = bus.subscribe()
    await hub.send_trusted_alert("CA1", message("CA1"))
    await hub.send_trusted_alert("CA2", message("CA2"))
    hub.on_alert_result("CA1", True, None)
    hub.on_alert_result("CA1", False, "send_failed")  # second answer ignored
    hub.on_alert_result("CA2", False, "no_permission")
    hub.on_alert_result("CA9", True, None)  # never alerted
    events = [sub.queue.get_nowait() for _ in range(sub.queue.qsize())]
    got = [(e["callId"], e["action"], e["detail"]) for e in events if e["type"] == "action"]
    assert got[2:] == [
        ("CA1", "sms_sent", "SMS sent by the senior's phone"),
        ("CA2", "sms_failed", "no_permission"),
    ]


def test_result_message_is_parsed():
    parsed = protocol.parse_app_message(
        json.dumps({"type": "alert_trusted_result", "callId": "CA1", "sent": False, "error": "x"})
    )
    assert isinstance(parsed, protocol.AlertTrustedResult) and parsed.error == "x"
    with pytest.raises(protocol.BadAppMessage):
        protocol.parse_app_message(
            json.dumps({"type": "alert_trusted_result", "callId": "bad id!", "sent": True})
        )


# ---------------------------------------------------------------------- end to end
def run_blocked_call(client, after_accept=None) -> str:
    """A scam call through the real stream and app channels until `scam_blocked`."""
    with client.websocket_connect("/twilio/stream") as stream:
        stream.send_json(start_message(admit(client)))
        assert wait_until(lambda: client.control.of_type("incoming_call"))
        incoming = client.control.of_type("incoming_call")[-1]
        url = f"/app/call/{incoming['callId']}?token={incoming['token']}"
        with client.websocket_connect(url) as app_ws:
            app_ws.send_json({"type": "accept"})
            if after_accept is not None:
                after_accept()
            for payload in speech_mulaw_frames():
                stream.send_json(media(payload))
            assert receive_json(app_ws, "call_ended")["reason"] == "scam_blocked"
        drain_until_close(stream)
    return incoming["callId"]


def test_blocked_call_sends_one_alert_on_the_control_channel(make_client):
    client = make_client(stt=FakeSTT([SCAM_TEXT]), decision_backend=scam_model())
    call_id = run_blocked_call(client)
    assert wait_until(lambda: client.control.of_type("alert_trusted"))
    alert = client.control.of_type("alert_trusted")[0]
    assert alert["callId"] == call_id and alert["scamType"] == "police"
    assert alert["lang"] == "pl" and {"money", "secrecy"} <= set(alert["reasons"])
    assert alert["text"].startswith("Sprawdzam: babcia") and alert["text"].isascii()
    assert len(client.control.of_type("alert_trusted")) == 1


def test_alert_reaches_a_real_control_socket_and_result_is_accepted(make_client):
    client = make_client(stt=FakeSTT([SCAM_TEXT]), decision_backend=scam_model(), app_online=False)
    hub = client.app.state.services.hub
    with client.websocket_connect(f"/app/control?device_token={DEVICE_TOKEN}") as control:
        receive_json(control, "protection_status")
        hub.add_control(client.control)  # records what the hub sends
        call_id = run_blocked_call(client)
        alert = receive_json(control, "alert_trusted")
        assert alert["callId"] == call_id
        control.send_json({"type": "alert_trusted_result", "callId": call_id, "sent": True})
        control.send_json({"type": "ping"})
        receive_json(control, "pong")
    assert call_id in hub._alert_results


def test_alert_queued_while_app_offline_is_delivered_on_connect(make_client):
    client = make_client(stt=FakeSTT([SCAM_TEXT]), decision_backend=scam_model())
    hub = client.app.state.services.hub
    # The control channel drops during the call (the call channel stays up).
    call_id = run_blocked_call(client, after_accept=lambda: hub.remove_control(client.control))
    assert client.control.of_type("alert_trusted") == []
    with client.websocket_connect(f"/app/control?device_token={DEVICE_TOKEN}") as control:
        receive_json(control, "protection_status")
        assert receive_json(control, "alert_trusted")["callId"] == call_id
    with client.websocket_connect(f"/app/control?device_token={DEVICE_TOKEN}") as control:
        receive_json(control, "protection_status")
        control.send_json({"type": "ping"})
        assert receive_json(control)["type"] == "pong"  # not delivered a second time
