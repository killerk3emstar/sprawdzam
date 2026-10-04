"""Live event stream for the jury / operator console (`WS /dev/events`, `GET /dev/alerts`)."""

import re

import pytest
from starlette.websockets import WebSocketDisconnect

from app.events import EventBus
from tests.conftest import (
    SCAM_TEXT,
    FakeSTT,
    admit,
    drain_until_close,
    media,
    receive_json,
    scam_model,
    speech_mulaw_frames,
    start_message,
    stop_message,
    wait_until,
)

ISO_MS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")


def drain(sub) -> list[dict]:
    return [sub.queue.get_nowait() for _ in range(sub.queue.qsize())]


# ---------------------------------------------------------------------- bus (unit)
def test_hello_and_slow_subscriber_drops_oldest():
    bus = EventBus(warn=40, hangup=80, queue_size=3)
    sub = bus.subscribe()
    assert sub.queue.get_nowait() == {"type": "hello", "warn": 40, "hangup": 80, "alerts": []}
    for i in range(5):
        bus.transcript("CA1", "caller", f"t{i}")  # never blocks, even with nobody reading
    events = drain(sub)
    assert [e["text"] for e in events] == ["t2", "t3", "t4"] and sub.dropped == 2
    assert all(ISO_MS.match(e["at"]) for e in events)
    sub.close()
    assert bus.subscriber_count == 0
    bus.transcript("CA1", "caller", "after close")  # no subscribers: fine


@pytest.mark.parametrize(
    ("levels", "reason", "outcome"),
    [
        (["none"], "caller_hangup", "normal"),
        (["none", "warn"], "caller_hangup", "warned"),
        (["warn", "high"], "scam_blocked", "blocked"),
    ],
)
def test_alert_summary(levels, reason, outcome):
    bus = EventBus()
    bus.call_started("CA1", "+48 *** *** 123", "pl")
    for i, level in enumerate(levels):
        bus.risk(
            "CA1",
            score=30 + 30 * i,
            model_score=None,
            rules_score=10,
            level=level,
            scam_type="police" if level != "none" else "none",
            reasons=["money"],
            source="rules",
        )
    bus.action("CA1", "warn", "x")
    alert = bus.call_ended("CA1", reason)
    assert alert is not None and alert["outcome"] == outcome
    assert alert["caller"] == "+48 *** *** 123" and alert["actions"] == ["warn"]
    assert alert["maxScore"] == 30 + 30 * (len(levels) - 1)
    assert set(alert) == {"callId", "at", "caller", "scamType", "maxScore", "outcome", "actions"}
    bus.action("CA1", "sms_sent", "later")  # after the call: the stored alert is updated
    assert bus.alert_list()[0]["actions"] == ["warn", "sms_sent"]


def test_trusted_or_unscored_calls_have_no_alert():
    bus = EventBus()
    bus.call_started("CA1", "+48 *** *** 123", "pl", analysed=False)
    assert bus.call_ended("CA1", "caller_hangup") is None
    bus.call_started("CA2", "+48 *** *** 123", "pl")
    assert bus.call_ended("CA2", "timeout") is None
    assert bus.alert_list() == []


def test_alert_list_keeps_last_50():
    bus = EventBus()
    for i in range(60):
        bus.call_started(f"CA{i}", "unknown", "en")
        bus.risk(
            f"CA{i}", score=1, model_score=1, rules_score=0, level="none",
            scam_type="none", reasons=[], source="model+rules",
        )  # fmt: skip
        bus.call_ended(f"CA{i}", "caller_hangup")
    alerts = bus.alert_list()
    assert len(alerts) == 50 and alerts[0]["callId"] == "CA10"


# ---------------------------------------------------------------------- routes
def test_event_routes_need_dev_tools(make_client):
    client = make_client()
    assert client.get("/dev/alerts").status_code == 404
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/dev/events") as ws:
        ws.receive_json()


def test_scam_call_events_reach_the_console(make_client, make_settings):
    client = make_client(
        make_settings(DEV_TOOLS=True), stt=FakeSTT([SCAM_TEXT]), decision_backend=scam_model()
    )
    with client.websocket_connect("/dev/events") as events:
        hello = events.receive_json()
        assert hello == {"type": "hello", "warn": 50, "hangup": 90, "alerts": []}
        with client.websocket_connect("/twilio/stream") as stream:
            stream.send_json(start_message(admit(client)))
            assert wait_until(lambda: client.control.of_type("incoming_call"))
            incoming = client.control.of_type("incoming_call")[-1]
            url = f"/app/call/{incoming['callId']}?token={incoming['token']}"
            with client.websocket_connect(url) as app_ws:
                app_ws.send_json({"type": "accept"})
                for payload in speech_mulaw_frames():
                    stream.send_json(media(payload))
                assert receive_json(app_ws, "call_ended")["reason"] == "scam_blocked"
            drain_until_close(stream)
        seen = []
        while not seen or seen[-1]["type"] != "action" or seen[-1]["action"] != "sms_requested":
            seen.append(events.receive_json())
    kinds = [e["type"] for e in seen]
    assert kinds[0] == "call_started" and "transcript" in kinds and "risk" in kinds
    started = seen[0]
    assert started["caller"] == "+48 *** *** 001" and started["lang"] == "pl"
    transcript = next(e for e in seen if e["type"] == "transcript")
    assert transcript["speaker"] == "caller" and "komisarz" in transcript["text"]
    risk = [e for e in seen if e["type"] == "risk"][-1]
    assert risk["level"] == "high" and risk["modelScore"] == 95 and risk["rulesScore"] >= 90
    assert risk["source"] == "model+rules" and risk["scamType"] == "police"
    actions = [e["action"] for e in seen if e["type"] == "action"]
    assert actions == ["verify_password", "password_failed", "hangup", "sms_requested"]
    ended = next(e for e in seen if e["type"] == "call_ended")
    assert ended["reason"] == "scam_blocked"
    alert = ended["alert"]
    assert alert["outcome"] == "blocked" and alert["scamType"] == "police"
    assert alert["maxScore"] >= 90 and "text" not in alert
    assert all(ISO_MS.match(e["at"]) for e in seen)
    stored = client.get("/dev/alerts").json()["alerts"]
    assert [a["callId"] for a in stored] == [incoming["callId"]]
    assert stored[0]["actions"][-1] == "sms_requested"
    assert SCAM_TEXT[:20] not in str(stored)  # no transcript in alerts


def test_console_gets_stored_alerts_on_connect(make_client, make_settings):
    client = make_client(make_settings(DEV_TOOLS=True), stt=FakeSTT(["Dzień dobry."]))
    with client.websocket_connect("/twilio/stream") as stream:
        stream.send_json(start_message(admit(client)))
        assert wait_until(lambda: client.control.of_type("incoming_call"))
        incoming = client.control.of_type("incoming_call")[-1]
        url = f"/app/call/{incoming['callId']}?token={incoming['token']}"
        with client.websocket_connect(url) as app_ws:
            app_ws.send_json({"type": "accept"})
            for payload in speech_mulaw_frames():
                stream.send_json(media(payload))
            assert wait_until(lambda: client.app.state.services.sessions and True, 1)
            receive_json(app_ws, "risk")
            stream.send_json(stop_message())
            receive_json(app_ws, "call_ended")
        drain_until_close(stream)
    with client.websocket_connect("/dev/events") as events:
        hello = events.receive_json()
    assert [a["outcome"] for a in hello["alerts"]] == ["normal"]
