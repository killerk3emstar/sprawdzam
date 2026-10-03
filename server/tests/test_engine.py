import logging

import httpx
import pytest

from app.risk.decision import DecisionBackendError
from app.risk.engine import RiskEngine
from app.risk.models import Action, ScamType
from app.transcript import TranscriptWindow
from tests.conftest import FakeDecision

pytestmark = pytest.mark.anyio

SCAM_PL = (
    "Mówi komisarz z CBŚ. Proszę wypłacić gotówkę i przekazać ją kurierowi. Nikomu o tym nie mówić."
)
FAMILY_PL = "Mamo, przelałem ci pieniądze za prąd, wpadnę w niedzielę."


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


def window(text: str) -> TranscriptWindow:
    transcript = TranscriptWindow()
    transcript.add("caller", text)
    return transcript


def engine_with(backend=None, timeout: float = 0.2) -> RiskEngine:
    return RiskEngine(
        warn_threshold=50,
        hangup_threshold=80,
        decision_backend=backend,
        decision_timeout_seconds=timeout,
    )


async def test_rules_only_when_no_backend():
    monitor = engine_with().start_call("CA1", "pl")
    result = await monitor.evaluate(window(SCAM_PL))
    assert result.source == "rules"
    assert result.fallback_reason == "not_configured"
    assert result.raw_score == result.rules.score >= 80
    assert result.scam_type is ScamType.POLICE


async def test_model_result_is_combined_with_rules():
    backend = FakeDecision({"risk": 90, "money": True, "scam_type": "bank"})
    monitor = engine_with(backend).start_call("CA1", "pl")
    result = await monitor.evaluate(window(FAMILY_PL))
    assert result.source == "model+rules"
    assert result.fallback_reason is None
    assert result.raw_score == 90  # max(model, rules)
    assert result.scam_type is ScamType.BANK
    assert result.categories["money"] is True
    assert backend.requests[0].state.startswith("caller: ")
    assert backend.requests[0].lang == "pl"


async def test_rules_win_when_model_says_low():
    backend = FakeDecision({"risk": 5})
    result = await engine_with(backend).start_call("CA1", "pl").evaluate(window(SCAM_PL))
    assert result.raw_score == result.rules.score >= 80


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
        (FakeDecision(exc=DecisionBackendError("bad json")), "http_error"),
        (FakeDecision({"unexpected": "shape"}), "malformed_response"),
        (FakeDecision("not a mapping"), "malformed_response"),
        (FakeDecision(None), "malformed_response"),
        (FakeDecision({"risk": "high"}), "malformed_response"),
        (FakeDecision({"risk": 150}), "out_of_range"),
        (FakeDecision({"risk": -1}), "out_of_range"),
        (FakeDecision({"risk": float("nan")}), "out_of_range"),
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


async def test_actions_escalate_once_and_need_two_high_readings():
    handler = RecordingHandler()
    monitor = engine_with().start_call("CA1", "pl", handler)
    first = await monitor.evaluate(window(SCAM_PL))
    assert first.level is Action.WARN  # one reading can only warn
    second = await monitor.evaluate(window(SCAM_PL))
    assert second.action is Action.VERIFY_THEN_HANGUP
    third = await monitor.evaluate(window(SCAM_PL))
    assert third.action is Action.NONE  # never repeated
    assert handler.actions == [Action.WARN, Action.VERIFY_THEN_HANGUP]


async def test_single_model_spike_never_hangs_up():
    handler = RecordingHandler()
    backend = FakeDecision({"risk": 100})
    monitor = engine_with(backend).start_call("CA1", "pl", handler)
    await monitor.evaluate(window(FAMILY_PL))
    backend.result = {"risk": 0}
    for _ in range(3):
        await monitor.evaluate(window(FAMILY_PL))
    assert handler.actions == [Action.WARN]


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
