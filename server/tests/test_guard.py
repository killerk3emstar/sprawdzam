import asyncio
import json
import logging
from datetime import date
from types import SimpleNamespace

import pytest

from app.risk.engine import RiskEngine
from app.risk.models import Action, ScamType
from app.telephony.guard import (
    DailyCounterStore,
    GuardConfig,
    GuardedCallActions,
    GuardOutcome,
)
from app.telephony.numbers import mask_number, parse_number_list
from app.telephony.responder import IncidentResponder, alert_sms
from app.transcript import TranscriptWindow
from tests.conftest import RecordingActions

pytestmark = pytest.mark.anyio

TRUSTED = "+48600000001"
OTHER = "+48600000002"
OWN = "+48100000000"


class FakeDay:
    def __init__(self, day: date = date(2026, 10, 4)) -> None:
        self.day = day

    def __call__(self) -> date:
        return self.day


def make_guard(tmp_path, inner=None, today=None, **config):
    defaults = {
        "dry_run": False,
        "allowlist": frozenset({TRUSTED, OWN}),
        "own_number": OWN,
        "max_calls_per_day": 10,
        "max_sms_per_day": 20,
    }
    defaults.update(config)
    store = DailyCounterStore(tmp_path, today=today or FakeDay())
    return GuardedCallActions(inner or RecordingActions(), GuardConfig(**defaults), store)


async def test_dry_run_is_default_and_executes_nothing(tmp_path):
    inner = RecordingActions()
    guard = GuardedCallActions(
        inner, GuardConfig(allowlist=frozenset({TRUSTED})), DailyCounterStore(tmp_path)
    )
    assert guard.config.dry_run is True
    assert await guard.call_trusted_person("CA1", TRUSTED, "msg") is GuardOutcome.DRY_RUN
    assert await guard.send_sms("CA1", TRUSTED, "msg") is GuardOutcome.DRY_RUN
    assert await guard.hang_up("CA1") is GuardOutcome.DRY_RUN
    assert inner.calls == []
    assert guard.counters.counts() == {"calls": 0, "sms": 0}


async def test_dry_run_logs_would_do(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    guard = make_guard(tmp_path, dry_run=True)
    await guard.send_sms("CA1", TRUSTED, "msg")
    assert any("telephony_would_sms" in r.getMessage() for r in caplog.records)


async def test_live_mode_executes_and_counts(tmp_path):
    inner = RecordingActions()
    guard = make_guard(tmp_path, inner)
    assert await guard.call_trusted_person("CA1", TRUSTED, "msg") is GuardOutcome.EXECUTED
    assert await guard.send_sms("CA1", TRUSTED, "msg") is GuardOutcome.EXECUTED
    assert inner.kinds() == ["call", "sms"]
    assert guard.counters.counts() == {"calls": 1, "sms": 1}


async def test_not_allowlisted_number_is_refused(tmp_path):
    inner = RecordingActions()
    guard = make_guard(tmp_path, inner)
    refused = GuardOutcome.REFUSED_NOT_ALLOWLISTED
    assert await guard.call_trusted_person("CA1", OTHER, "m") is refused
    assert await guard.send_sms("CA1", OTHER, "m") is refused
    assert inner.calls == []


async def test_own_number_is_refused_even_if_allowlisted(tmp_path):
    inner = RecordingActions()
    guard = make_guard(tmp_path, inner)
    assert await guard.call_trusted_person("CA1", OWN, "m") is GuardOutcome.REFUSED_OWN_NUMBER
    assert await guard.send_sms("CA1", OWN, "m") is GuardOutcome.REFUSED_OWN_NUMBER
    assert inner.calls == []


@pytest.mark.parametrize("number", ["600000001", "+0123456789", "+48 600", "", "+48abc"])
async def test_invalid_numbers_are_refused(tmp_path, number):
    guard = make_guard(tmp_path)
    outcome = await guard.call_trusted_person("CA1", number, "m")
    assert outcome is GuardOutcome.REFUSED_INVALID_NUMBER


async def test_one_call_and_one_sms_per_incident(tmp_path):
    inner = RecordingActions()
    guard = make_guard(tmp_path, inner)
    for _ in range(5):
        await guard.call_trusted_person("CA1", TRUSTED, "m")
        await guard.send_sms("CA1", TRUSTED, "m")
        await guard.hang_up("CA1")
    assert inner.kinds() == ["call", "sms", "hang_up"]
    # A different incoming call is a new incident.
    assert await guard.call_trusted_person("CA2", TRUSTED, "m") is GuardOutcome.EXECUTED
    assert guard.counters.counts() == {"calls": 2, "sms": 1}


async def test_daily_cap_persists_across_restarts(tmp_path):
    day = FakeDay()
    guard = make_guard(tmp_path, today=day, max_calls_per_day=2, max_sms_per_day=1)
    assert await guard.call_trusted_person("CA1", TRUSTED, "m") is GuardOutcome.EXECUTED
    assert await guard.call_trusted_person("CA2", TRUSTED, "m") is GuardOutcome.EXECUTED
    assert await guard.call_trusted_person("CA3", TRUSTED, "m") is GuardOutcome.REFUSED_DAILY_CAP
    assert await guard.send_sms("CA1", TRUSTED, "m") is GuardOutcome.EXECUTED
    assert await guard.send_sms("CA2", TRUSTED, "m") is GuardOutcome.REFUSED_DAILY_CAP

    # "Restart": a fresh guard and store reading the same data dir keep the counts.
    inner = RecordingActions()
    fresh = make_guard(tmp_path, inner, today=day, max_calls_per_day=2, max_sms_per_day=1)
    assert await fresh.call_trusted_person("CA4", TRUSTED, "m") is GuardOutcome.REFUSED_DAILY_CAP
    assert await fresh.send_sms("CA4", TRUSTED, "m") is GuardOutcome.REFUSED_DAILY_CAP
    assert inner.calls == []

    # The next day the counters start again.
    day.day = date(2026, 10, 5)
    assert await fresh.call_trusted_person("CA5", TRUSTED, "m") is GuardOutcome.EXECUTED


async def test_counter_file_holds_only_date_and_counts(tmp_path):
    guard = make_guard(tmp_path)
    await guard.call_trusted_person("CA1", TRUSTED, "secret message")
    raw = (tmp_path / DailyCounterStore.FILENAME).read_text()
    assert json.loads(raw) == {"date": "2026-10-04", "calls": 1, "sms": 0}
    assert TRUSTED not in raw


async def test_corrupt_counter_file_fails_closed(tmp_path):
    (tmp_path / DailyCounterStore.FILENAME).write_text("{not json")
    inner = RecordingActions()
    guard = make_guard(tmp_path, inner)
    outcome = await guard.call_trusted_person("CA1", TRUSTED, "m")
    assert outcome is GuardOutcome.REFUSED_COUNTER_ERROR
    assert inner.calls == []
    assert guard.status()["today"] == "unavailable"


async def test_inner_failure_is_reported_not_raised(tmp_path):
    guard = make_guard(tmp_path, RecordingActions(fail={"call"}))
    assert await guard.call_trusted_person("CA1", TRUSTED, "m") is GuardOutcome.FAILED
    # The spend was reserved before the attempt (conservative).
    assert guard.counters.counts()["calls"] == 1


async def test_logs_mask_phone_numbers(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    guard = make_guard(tmp_path)
    await guard.call_trusted_person("CA1", OTHER, "m")
    await guard.call_trusted_person("CA2", TRUSTED, "m")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert OTHER not in text and TRUSTED not in text
    assert mask_number(OTHER) in text


def test_status_exposes_limits_not_numbers(tmp_path):
    status = make_guard(tmp_path).status()
    assert status["allowlist_size"] == 2
    assert TRUSTED not in json.dumps(status)


def test_number_helpers():
    assert parse_number_list(" +48600000001, +15551234567 ,") == {"+48600000001", "+15551234567"}
    with pytest.raises(ValueError):
        parse_number_list("+48600000001, 600000002")
    assert mask_number("+48600000001") == "+48*******01"


class FakeCall:
    """CallControl fake for the responder."""

    def __init__(self, password_ok: bool = False) -> None:
        self.events: list[str] = []
        self.password_ok = password_ok
        self.tasks: list[asyncio.Task] = []

    async def send_risk(self, assessment) -> None:
        self.events.append(f"risk:{assessment.level.value}")

    async def play_warning(self) -> None:
        self.events.append("warning_tone")

    async def verify_family_password(self, warn_first: bool = False) -> bool:
        self.events.append("verify_password+warning" if warn_first else "verify_password")
        return self.password_ok

    async def play_blocked_notice(self) -> None:
        self.events.append("blocked_notice")

    async def end(self, reason) -> None:
        self.events.append(f"end:{reason.value}")

    def spawn_background(self, coro):
        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task


async def test_responder_full_incident_through_guard(tmp_path):
    inner = RecordingActions()
    guard = make_guard(tmp_path, inner)
    call = FakeCall()
    engine = RiskEngine(warn_threshold=50, hangup_threshold=90)
    monitor = engine.start_call("CA1", "pl", IncidentResponder(call, guard, "pl", TRUSTED))
    transcript = TranscriptWindow()
    transcript.add("caller", "Jestem z CBŚ, proszę przekazać gotówkę kurierowi, nikomu nie mów.")
    for _ in range(6):  # many high readings
        await monitor.evaluate(transcript)
    await asyncio.gather(*call.tasks)
    # Straight to the password check (two readings >= 90 + rule hit); the senior hears the
    # warning first because there was no warn step.
    assert call.events[:2] == ["risk:none", "risk:verify_family_password_then_hangup"]
    assert call.events.count("verify_password+warning") == 1
    assert call.events[-2:] == ["blocked_notice", "end:scam_blocked"]
    assert inner.kinds() == ["hang_up", "call", "sms"]


async def test_responder_warn_then_verify_skips_second_warning(tmp_path):
    call = FakeCall()
    responder = IncidentResponder(call, make_guard(tmp_path, RecordingActions()), "pl", "")
    common = {"call_id": "CA1", "scam_type": ScamType.POLICE}
    warn = SimpleNamespace(level=Action.WARN, action=Action.WARN, smoothed_score=60, **common)
    high = SimpleNamespace(
        level=Action.VERIFY_THEN_HANGUP,
        action=Action.VERIFY_THEN_HANGUP,
        smoothed_score=95,
        **common,
    )
    await responder.handle(warn)
    await responder.handle(high)
    await asyncio.gather(*call.tasks)
    assert call.events[:3] == [
        "risk:warn",
        "warning_tone",
        "risk:verify_family_password_then_hangup",
    ]
    assert "verify_password" in call.events  # no second warning before the prompt


async def test_responder_password_ok_clears_incident(tmp_path):
    inner = RecordingActions()
    call = FakeCall(password_ok=True)
    responder = IncidentResponder(call, make_guard(tmp_path, inner), "pl", TRUSTED)
    await responder.verify_or_block(
        SimpleNamespace(call_id="CA1", smoothed_score=95, scam_type=ScamType.POLICE)
    )
    assert call.events == ["verify_password"]
    assert inner.calls == []


async def test_responder_without_trusted_person_only_hangs_up(tmp_path):
    inner = RecordingActions()
    call = FakeCall()
    responder = IncidentResponder(call, make_guard(tmp_path, inner), "en", "")
    await responder.verify_or_block(
        SimpleNamespace(call_id="CA1", smoothed_score=95, scam_type=ScamType.BANK)
    )
    assert call.events == ["verify_password", "blocked_notice", "end:scam_blocked"]
    assert inner.kinds() == ["hang_up"]


async def test_responder_continues_after_failed_step(tmp_path):
    inner = RecordingActions(fail={"hang_up"})
    responder = IncidentResponder(FakeCall(), inner, "pl", TRUSTED)
    assessment = SimpleNamespace(call_id="CA1", smoothed_score=91, scam_type=ScamType.POLICE)
    await responder.verify_or_block(assessment)
    assert inner.kinds() == ["hang_up", "call", "sms"]
    sms = alert_sms(assessment, "pl")
    assert "91/100" in sms and "policjanta" in sms
