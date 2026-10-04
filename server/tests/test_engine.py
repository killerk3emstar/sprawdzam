import logging

import httpx
import pytest

from app.risk.decision import SIGNALS, DecisionBackendError, MalformedDecision
from app.risk.engine import RiskEngine
from app.risk.models import Action, ScamType
from app.transcript import TranscriptWindow
from tests.conftest import FakeDecision

pytestmark = pytest.mark.anyio

SCAM_PL = (
    "Mówi komisarz z CBŚ. Proszę wypłacić gotówkę i przekazać ją kurierowi. Nikomu o tym nie mówić."
)
FAMILY_PL = "Mamo, przelałem ci pieniądze za prąd, wpadnę w niedzielę."
QUICK = {"risk": 95.0, "scam_type": "police"}
FULL = {**QUICK, "money": 0.9, "secrecy": 0.95, "authority": 0.9, "urgency": 0.9}


class RecordingHandler:
    """ActionHandler fake: records every assessment and the actions that fired."""

    def __init__(self, fail: bool = False) -> None:
        self.assessments = []
        self.actions: list[Action] = []
        self.fail = fail

    async def handle(self, assessment):
        self.assessments.append(assessment)
        if assessment.action is not Action.NONE:
            self.actions.append(assessment.action)
        if self.fail:
            raise RuntimeError("boom")


class TwoTierDecision(FakeDecision):
    """Answers quick requests with `quick`, full ones with `full`."""

    def __init__(self, quick: dict, full: dict | None = None) -> None:
        super().__init__(quick)
        self.quick, self.full = quick, full

    async def assess(self, request):
        self.requests.append(request)
        return self.full if request.full else self.quick


def window(text: str) -> TranscriptWindow:
    transcript = TranscriptWindow()
    transcript.add("caller", text)
    return transcript


def engine_with(backend=None, timeout: float = 0.2) -> RiskEngine:
    return RiskEngine(
        warn_threshold=50,
        hangup_threshold=90,
        secrecy_hangup_min=0.8,
        decision_backend=backend,
        decision_timeout_seconds=timeout,
    )


async def test_rules_only_when_no_backend():
    monitor = engine_with().start_call("CA1", "pl")
    result = await monitor.evaluate(window(SCAM_PL))
    assert result.source == "rules"
    assert result.fallback_reason == "not_configured"
    assert result.raw_score == result.rules.score >= 90
    assert result.scam_type is ScamType.POLICE
    assert result.rule_hit


async def test_model_result_is_combined_with_rules():
    backend = FakeDecision({"risk": 90, "scam_type": "bank"})
    monitor = engine_with(backend).start_call("CA1", "pl")
    result = await monitor.evaluate(window(FAMILY_PL))
    assert result.source == "model+rules"
    assert result.fallback_reason is None
    assert result.raw_score == 90  # max(model, rules)
    assert result.scam_type is ScamType.BANK
    request = backend.requests[0]
    assert request.state.startswith("Dzwoniący: ") and request.lang == "pl"
    assert request.full is False


async def test_english_state_uses_english_speaker_tag():
    backend = FakeDecision({"risk": 1})
    await engine_with(backend).start_call("CA1", "en").evaluate(window("Hello"))
    assert backend.requests[0].state == "Caller: Hello"


async def test_rules_win_when_model_says_low():
    backend = FakeDecision({"risk": 5})
    result = await engine_with(backend).start_call("CA1", "pl").evaluate(window(SCAM_PL))
    assert result.raw_score == result.rules.score >= 90


@pytest.mark.parametrize(
    ("backend", "reason"),
    [
        (FakeDecision({"risk": 10}, delay=1.0), "timeout"),
        (FakeDecision(exc=httpx.ConnectError("connection refused")), "http_error"),
        (
            FakeDecision(
                exc=httpx.HTTPStatusError(
                    "server error",
                    request=httpx.Request("POST", "http://basal.invalid/v1/systemone"),
                    response=httpx.Response(503),
                )
            ),
            "http_error",
        ),
        (FakeDecision(exc=DecisionBackendError("HTTP 422: bad schema")), "http_error"),
        (FakeDecision(exc=DecisionBackendError("timeout")), "timeout"),
        (FakeDecision(exc=MalformedDecision("missing answers")), "malformed_response"),
        (FakeDecision({"unexpected": "shape"}), "malformed_response"),
        (FakeDecision("not a mapping"), "malformed_response"),
        (FakeDecision(None), "malformed_response"),
        (FakeDecision({"risk": "high"}), "malformed_response"),
        (FakeDecision({"risk": 50, "scam_type": "pirates"}), "malformed_response"),
        (FakeDecision({"risk": 150}), "out_of_range"),
        (FakeDecision({"risk": -1}), "out_of_range"),
        (FakeDecision({"risk": float("nan")}), "out_of_range"),
        (FakeDecision({"risk": 50, "secrecy": 1.5}), "out_of_range"),
        (FakeDecision(exc=RuntimeError("client bug")), "unexpected_error"),
    ],
)
async def test_backend_failures_fall_back_to_rules(backend, reason, caplog):
    caplog.set_level(logging.WARNING, logger="app.risk.engine")
    monitor = engine_with(backend, timeout=0.05).start_call("CA1", "pl")
    result = await monitor.evaluate(window(SCAM_PL))
    assert result.source == "rules"
    assert result.fallback_reason == reason
    assert result.model is None
    assert result.raw_score == result.rules.score
    assert any(
        "decision_fallback_to_rules" in r.getMessage() and reason in r.getMessage()
        for r in caplog.records
    )


async def test_two_tier_full_request_once_after_warn_reading():
    backend = TwoTierDecision({"risk": 10.0, "scam_type": "none"}, FULL)
    monitor = engine_with(backend).start_call("CA1", "pl")
    await monitor.evaluate(window(FAMILY_PL))  # quick, low
    backend.quick = QUICK
    await monitor.evaluate(window(FAMILY_PL))  # quick, crosses warn
    result = await monitor.evaluate(window(FAMILY_PL))  # full, once
    for _ in range(3):
        await monitor.evaluate(window(FAMILY_PL))  # quick again
    assert [r.full for r in backend.requests] == [False, False, True, False, False, False]
    assert result.full_request and result.signals["secrecy"] == 0.95
    assert monitor.signals == {"money": 0.9, "secrecy": 0.95, "authority": 0.9, "urgency": 0.9}


async def test_failed_full_request_is_retried_once():
    backend = TwoTierDecision(QUICK, full={"risk": 95})  # full answer without signals
    monitor = engine_with(backend).start_call("CA1", "pl")
    for _ in range(5):
        await monitor.evaluate(window(FAMILY_PL))
    assert [r.full for r in backend.requests] == [False, True, True, False, False]
    assert monitor.signals == {}


async def test_warn_needs_two_readings_in_a_row():
    handler = RecordingHandler()
    backend = FakeDecision({"risk": 60})
    monitor = engine_with(backend).start_call("CA1", "pl", handler)
    first = await monitor.evaluate(window(FAMILY_PL))
    assert first.level is Action.NONE
    second = await monitor.evaluate(window(FAMILY_PL))
    assert second.action is Action.WARN
    assert handler.actions == [Action.WARN]


async def test_hangup_needs_secrecy_money_or_rule_hit():
    # Model says 95 every time, but the full answer has no secrecy and no money ask and the
    # text has no keyword-rule hit: warn only, never the password check / hang-up.
    handler = RecordingHandler()
    backend = TwoTierDecision(QUICK, {**FULL, "secrecy": 0.1, "money": 0.1})
    monitor = engine_with(backend).start_call("CA1", "pl", handler)
    results = [await monitor.evaluate(window(FAMILY_PL)) for _ in range(5)]
    assert not results[-1].rule_hit
    assert handler.actions == [Action.WARN]
    assert results[-1].level is Action.WARN


async def test_hangup_with_model_money_ask_without_secrecy():
    # A live grandchild scam without "don't tell anyone": model 95+ and it reads a money ask.
    handler = RecordingHandler()
    backend = TwoTierDecision(QUICK, {**FULL, "secrecy": 0.25, "money": 0.63})
    monitor = engine_with(backend).start_call("CA1", "pl", handler)
    for _ in range(3):
        await monitor.evaluate(window(FAMILY_PL))
    assert handler.actions == [Action.VERIFY_THEN_HANGUP]


async def test_hangup_with_model_secrecy():
    handler = RecordingHandler()
    backend = TwoTierDecision(QUICK, FULL)
    monitor = engine_with(backend).start_call("CA1", "pl", handler)
    results = [await monitor.evaluate(window(FAMILY_PL)) for _ in range(3)]
    # reading 1: quick 95; reading 2: full (secrecy 0.95 cached) and second reading >= 90
    assert results[1].full_request
    assert results[1].action is Action.VERIFY_THEN_HANGUP
    assert handler.actions == [Action.VERIFY_THEN_HANGUP]


async def test_rules_alone_warn_but_never_hang_up_when_model_is_down():
    handler = RecordingHandler()
    monitor = engine_with(FakeDecision(exc=httpx.ConnectError("down"))).start_call(
        "CA1", "pl", handler
    )
    results = [await monitor.evaluate(window(SCAM_PL)) for _ in range(5)]
    assert all(r.source == "rules" for r in results)
    assert results[0].level is Action.NONE  # one reading is never enough
    assert results[1].raw_score >= 90 and results[1].rule_hit
    assert results[1].action is Action.WARN
    assert handler.actions == [Action.WARN]  # never escalates to the hang-up


async def test_rules_only_engine_never_hangs_up():
    handler = RecordingHandler()
    monitor = engine_with().start_call("CA1", "pl", handler)
    for _ in range(5):
        result = await monitor.evaluate(window(SCAM_PL))
    assert result.level is Action.WARN
    assert handler.actions == [Action.WARN]


async def test_rules_high_but_model_low_only_warns():
    """Negation the rules cannot read: the model says it is fine, the rules score high."""
    handler = RecordingHandler()
    backend = FakeDecision({"risk": 20.0, "scam_type": "none", **{k: 0.1 for k in SIGNALS}})
    monitor = engine_with(backend).start_call("CA1", "pl", handler)
    for _ in range(5):
        result = await monitor.evaluate(window(SCAM_PL))
    assert result.raw_score >= 90 and result.rule_hit
    assert handler.actions == [Action.WARN]


async def test_model_drop_breaks_the_hangup_streak():
    handler = RecordingHandler()
    backend = FakeDecision(FULL)
    monitor = engine_with(backend).start_call("CA1", "pl", handler)
    await monitor.evaluate(window(SCAM_PL))  # model 95
    backend.exc = httpx.ConnectError("down")
    await monitor.evaluate(window(SCAM_PL))  # model down, rules 100
    backend.exc = None
    result = await monitor.evaluate(window(SCAM_PL))  # model 95 again, only one in a row
    assert result.level is Action.WARN
    result = await monitor.evaluate(window(SCAM_PL))
    assert result.action is Action.VERIFY_THEN_HANGUP
    assert handler.actions == [Action.WARN, Action.VERIFY_THEN_HANGUP]


async def test_model_high_with_rule_hit_hangs_up():
    handler = RecordingHandler()
    # Quick answers only (no signals), so the gate is opened by the rule hit, not secrecy.
    backend = FakeDecision({"risk": 95.0, "scam_type": "police"})
    monitor = engine_with(backend).start_call("CA1", "pl", handler)
    results = [await monitor.evaluate(window(SCAM_PL)) for _ in range(3)]
    assert results[0].level is Action.NONE
    assert results[1].action is Action.VERIFY_THEN_HANGUP
    assert results[2].action is Action.NONE  # never repeated
    assert handler.actions == [Action.VERIFY_THEN_HANGUP]


async def test_single_model_spike_triggers_nothing():
    handler = RecordingHandler()
    backend = FakeDecision({"risk": 100})
    monitor = engine_with(backend).start_call("CA1", "pl", handler)
    await monitor.evaluate(window(FAMILY_PL))
    backend.result = {"risk": 0}
    for _ in range(3):
        await monitor.evaluate(window(FAMILY_PL))
    assert handler.actions == []


async def test_normal_call_triggers_nothing():
    handler = RecordingHandler()
    monitor = engine_with().start_call("CA1", "pl", handler)
    for _ in range(5):
        result = await monitor.evaluate(window(FAMILY_PL))
    assert result.level is Action.NONE
    assert handler.actions == []
    assert len(handler.assessments) == 5  # every assessment reaches the handler


async def test_failing_action_handler_does_not_break_evaluation(caplog):
    monitor = engine_with().start_call("CA1", "pl", RecordingHandler(fail=True))
    await monitor.evaluate(window(SCAM_PL))
    result = await monitor.evaluate(window(SCAM_PL))
    assert result.action is Action.WARN
    assert any("action_failed" in r.getMessage() for r in caplog.records)


async def test_logs_never_contain_transcript_text(caplog):
    caplog.set_level(logging.DEBUG)
    backend = FakeDecision({"risk": 150})
    monitor = engine_with(backend).start_call("CA1", "pl", RecordingHandler())
    await monitor.evaluate(window(SCAM_PL))
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "risk_assessment" in log_text
    for fragment in ("komisarz", "kurierowi", "gotówkę", "Nikomu"):
        assert fragment not in log_text


def test_invalid_thresholds_rejected():
    with pytest.raises(ValueError):
        RiskEngine(warn_threshold=80, hangup_threshold=50)


async def test_stale_secrecy_is_refreshed_when_enabled():
    now = [0.0]
    backend = TwoTierDecision(QUICK, {**FULL, "secrecy": 0.1, "money": 0.1})
    engine = RiskEngine(decision_backend=backend, full_refresh_seconds=10, clock=lambda: now[0])
    handler = RecordingHandler()
    monitor = engine.start_call("CA1", "pl", handler)
    for _ in range(3):  # quick, full (secrecy 0.1), quick -> gate blocked
        await monitor.evaluate(window(FAMILY_PL))
        now[0] += 4
    assert handler.actions == [Action.WARN]
    backend.full = FULL  # secrecy said later in the call
    for _ in range(3):
        await monitor.evaluate(window(FAMILY_PL))
        now[0] += 4
    assert [r.full for r in backend.requests].count(True) == 2
    assert handler.actions == [Action.WARN, Action.VERIFY_THEN_HANGUP]


async def test_full_set_is_asked_once_by_default():
    backend = TwoTierDecision(QUICK, {**FULL, "secrecy": 0.1})
    monitor = engine_with(backend).start_call("CA1", "pl")
    for _ in range(8):
        await monitor.evaluate(window(FAMILY_PL))
    assert [r.full for r in backend.requests].count(True) == 1
