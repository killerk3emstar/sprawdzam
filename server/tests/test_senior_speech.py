"""The senior's microphone is transcribed too (speaker "senior"), with an echo guard."""

import asyncio
import logging

import numpy as np
import pytest

from app.echo_guard import EchoGuard
from app.events import EventBus
from app.risk.engine import RiskEngine
from app.session import CallSession
from tests.conftest import (
    SCAM_TEXT,
    FakeSTT,
    admit,
    drain_until_close,
    media,
    receive_json,
    speech_mulaw_frames,
    start_message,
    stop_message,
    wait_until,
)

pytestmark = pytest.mark.anyio

CALLER = "Babciu, miałem wypadek, potrzebuję pieniędzy na kaucję."
SENIOR = "A kto mówi? Zadzwonię do syna."


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


# ---------------------------------------------------------------------- echo guard
def test_echo_guard_matches_similar_and_contained_text():
    clock = Clock()
    guard = EchoGuard(clock=clock)
    guard.add_caller(CALLER)
    assert guard.is_echo("babciu miałem wypadek potrzebuję pieniędzy na kaucję")  # same words
    assert guard.is_echo("Miałem wypadek, potrzebuję pieniędzy")  # contained
    assert guard.is_echo("Babciu, miałem wypadek, potrzebuje pieniedzy na kaucje!")  # ratio
    assert not guard.is_echo(SENIOR)
    assert not guard.is_echo("Tak.")  # short answers are never treated as echo
    clock.now += 16  # older than the 15 s window
    assert not guard.is_echo(CALLER)


def test_echo_guard_spanning_two_caller_utterances():
    guard = EchoGuard()
    guard.add_caller("Proszę wypłacić wszystkie oszczędności z konta.")
    guard.add_caller("Kurier przyjedzie po nie za godzinę.")
    assert guard.is_echo("oszczędności z konta kurier przyjedzie po nie")


# ---------------------------------------------------------------------- session (fakes)
class ScriptedSTT:
    """Answers by speaker, told apart by the segment's amplitude (caller 0.3, senior 0.6)."""

    name = "scripted"

    def __init__(self, caller: list[str], senior: list[str], delay: float = 0.0) -> None:
        self.caller, self.senior, self.delay = list(caller), list(senior), delay
        self.order: list[str] = []

    async def transcribe(self, audio, rate, lang):
        if self.delay:
            await asyncio.sleep(self.delay)
        who = "senior" if float(np.max(np.abs(audio))) > 0.45 else "caller"
        self.order.append(who)
        source = self.senior if who == "senior" else self.caller
        return source.pop(0) if source else ""


def tone(seconds: float, amplitude: float) -> np.ndarray:
    t = np.arange(int(seconds * 16000)) / 16000
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def make_session(stt, events=None, analyse_senior=True) -> CallSession:
    monitor = RiskEngine().start_call("CA1", "pl")
    return CallSession(
        call_sid="CA1",
        stream_sid="MZ1",
        lang="pl",
        stt=stt,
        monitor=monitor,
        events=events,
        analyse_senior=analyse_senior,
    )


async def wait_for(predicate, limit: float = 3.0) -> None:
    for _ in range(int(limit / 0.01)):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met")


async def test_senior_utterances_join_the_transcript_and_events():
    bus = EventBus()
    sub = bus.subscribe()
    stt = ScriptedSTT([CALLER], [SENIOR])
    session = make_session(stt, events=bus)
    session.start()
    session._enqueue("caller", tone(3.5, 0.3))
    await wait_for(lambda: len(session.transcript) == 1)
    session._enqueue("senior", tone(2.0, 0.6))
    await wait_for(lambda: len(session.transcript) == 2)
    rendered = session.transcript.render("pl")
    assert rendered.splitlines() == [f"Dzwoniący: {CALLER}", f"Senior: {SENIOR}"]
    events = [e for e in (sub.queue.get_nowait() for _ in range(sub.queue.qsize()))]
    speakers = [e["speaker"] for e in events if e["type"] == "transcript"]
    assert speakers == ["caller", "senior"]
    await session.close()


async def test_echo_of_the_caller_is_dropped(caplog):
    caplog.set_level(logging.INFO)
    stt = ScriptedSTT([CALLER], ["Babciu, miałem wypadek, potrzebuję pieniędzy na kaucję."])
    session = make_session(stt)
    session.start()
    session._enqueue("caller", tone(3.5, 0.3))
    session._enqueue("senior", tone(3.5, 0.6))
    await wait_for(lambda: session.stats["echo_dropped"] == 1)
    assert session.transcript.render("pl").splitlines() == [f"Dzwoniący: {CALLER}"]
    assert any("echo_dropped" in r.getMessage() for r in caplog.records)
    assert "wypadek" not in caplog.text  # no transcript text in logs
    await session.close()


async def test_caller_segments_go_first():
    stt = ScriptedSTT(["a", "b"], ["c"], delay=0.05)
    session = make_session(stt)
    # Queue before the worker starts: senior first in time, but the caller has priority.
    session._enqueue("senior", tone(2.0, 0.6))
    session._enqueue("caller", tone(3.5, 0.3))
    session._enqueue("caller", tone(3.5, 0.3))
    session.start()
    await wait_for(lambda: len(stt.order) == 3)
    assert stt.order == ["caller", "caller", "senior"]
    await session.close()


async def test_senior_waits_while_the_caller_is_mid_utterance(monkeypatch):
    monkeypatch.setattr("app.session.SENIOR_HOLD_SECONDS", 0.3)
    stt = ScriptedSTT([], ["c"])
    session = make_session(stt)
    session.start()
    session.segmenter.push(tone(1.0, 0.3))  # caller speaking, no segment cut yet
    assert session.segmenter.in_segment
    session._enqueue("senior", tone(2.0, 0.6))
    await asyncio.sleep(0.15)
    assert stt.order == []  # held
    await wait_for(lambda: stt.order == ["senior"])  # released after the hold limit
    await session.close()


async def test_senior_audio_feed_segments_pcm16():
    stt = ScriptedSTT([], [SENIOR])
    session = make_session(stt)
    session.start()
    pcm = (tone(2.0, 0.6) * 32767).astype("<i2").tobytes()
    silence = bytes(640 * 75)  # 1.5 s
    for chunk in [pcm[i : i + 640] for i in range(0, len(pcm), 640)] + [silence]:
        session.feed_senior_pcm16(chunk)
    await wait_for(lambda: len(session.transcript) == 1)
    assert session.stats["senior_segments"] == 1
    await session.close()


async def test_senior_analysis_can_be_disabled():
    session = make_session(ScriptedSTT([], [SENIOR]), analyse_senior=False)
    session.feed_senior_pcm16((tone(2.0, 0.6) * 32767).astype("<i2").tobytes() + bytes(64000))
    assert not session._pending["senior"]
    await session.close()


# ---------------------------------------------------------------------- end to end
def test_app_microphone_is_transcribed_as_senior(make_client):
    stt = FakeSTT([SCAM_TEXT, "Nie mam pieniędzy w domu, zadzwonię na policję."])
    client = make_client(stt=stt)
    session_ref = {}
    with client.websocket_connect("/twilio/stream") as stream:
        stream.send_json(start_message(admit(client)))
        assert wait_until(lambda: client.control.of_type("incoming_call"))
        incoming = client.control.of_type("incoming_call")[-1]
        session_ref["s"] = client.app.state.services.sessions[incoming["callId"]]
        url = f"/app/call/{incoming['callId']}?token={incoming['token']}"
        with client.websocket_connect(url) as app_ws:
            app_ws.send_json({"type": "accept"})
            for payload in speech_mulaw_frames(bursts=(3.5,)):
                stream.send_json(media(payload))
            receive_json(app_ws, "risk")
            pcm = (tone(2.0, 0.6) * 32767).astype("<i2").tobytes() + bytes(640 * 75)
            for i in range(0, len(pcm), 640):
                app_ws.send_bytes(pcm[i : i + 640])
            session = session_ref["s"]
            assert wait_until(lambda: len(session.transcript) == 2)
            lines = session.transcript.render("pl").splitlines()
            assert lines[1].startswith("Senior: Nie mam pieniędzy")
            stream.send_json(stop_message())
            receive_json(app_ws, "call_ended")
        drain_until_close(stream)
