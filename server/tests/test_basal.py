import json

import httpx
import pytest

from app.risk.basal import BasalBackend, build_questions, load_schema, parse_response
from app.risk.decision import DecisionBackendError, DecisionRequest, MalformedDecision
from app.risk.engine import RiskEngine
from app.transcript import TranscriptWindow

pytestmark = pytest.mark.anyio


def answers(low: float = 0.01, choice: str = "police", secrecy: float = 0.97) -> dict:
    def noul(p):
        return {"type": "noul", "noul": p, "probabilities": {"true": p, "false": 1 - p}}

    return {
        "model": "basal-1.0-4.5B",
        "answers": {
            "risk": {
                "type": "score",
                "score": 1.9,
                "probabilities": {"low": low, "medium": 0.1, "high": 0.8, "critical": 0.09},
            },
            "scam_type": {
                "type": "choice",
                "choice": choice,
                "probabilities": {"none": 0.01, "police": 0.9},
            },
            "money": noul(0.9),
            "secrecy": noul(secrecy),
            "authority": noul(0.8),
            "urgency": noul(0.7),
        },
        "usage": {"latency_ms": 1000},
    }


def backend_with(handler) -> BasalBackend:
    return BasalBackend(
        "http://basal.test",
        timeout=0.5,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def request(full: bool = False, lang: str = "pl") -> DecisionRequest:
    return DecisionRequest(call_id="CA1", lang=lang, state="Dzwoniący: test", full=full)


def test_schemas_and_question_tiers():
    for lang in ("pl", "en"):
        schema = load_schema(lang)
        assert set(schema) == {"money", "secrecy", "authority", "urgency", "scam_type", "risk"}
        assert schema["risk"]["option_keys"] == "hide"
    assert set(build_questions("pl", full=False)) == {"risk", "scam_type"}
    assert len(build_questions("en", full=True)) == 6
    assert "dzwoniący" in build_questions("pl", full=True)["money"]["instructions"]


async def test_quick_request_maps_risk_not_low():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, json=answers(low=0.2))

    result = await backend_with(handler).assess(request())
    assert seen["url"] == "http://basal.test/v1/systemone"
    assert set(seen["body"]["questions"]) == {"risk", "scam_type"}
    assert seen["body"]["state"] == "Dzwoniący: test"
    assert result == {"risk": pytest.approx(80.0), "scam_type": "police"}


async def test_full_request_returns_signal_probabilities():
    result = await backend_with(lambda r: httpx.Response(200, json=answers())).assess(
        request(full=True, lang="en")
    )
    assert result["secrecy"] == pytest.approx(0.97)
    assert result["money"] == pytest.approx(0.9)
    assert result["risk"] == pytest.approx(99.0)


@pytest.mark.parametrize(
    ("response", "error", "match"),
    [
        (
            httpx.Response(422, json={"error": "questions: wrong option count"}),
            DecisionBackendError,
            "HTTP 422: questions: wrong option count",
        ),
        (httpx.Response(500, text="oops"), DecisionBackendError, "HTTP 500"),
        (httpx.Response(200, text="{not json"), MalformedDecision, "invalid JSON"),
        (httpx.Response(200, json={"answers": {}}), MalformedDecision, "missing answer: risk"),
        (httpx.Response(200, json={"nope": 1}), MalformedDecision, "missing answers"),
    ],
)
async def test_errors(response, error, match):
    with pytest.raises(error, match=match):
        await backend_with(lambda r: response).assess(request())


async def test_timeout_is_reported():
    def slow(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(DecisionBackendError, match="timeout"):
        await backend_with(slow).assess(request())


def test_parse_shape_errors():
    broken = answers()
    broken["answers"]["risk"]["probabilities"] = {"medium": 1.0}
    with pytest.raises(MalformedDecision, match="P\\(low\\)"):
        parse_response(broken, full=False)
    broken = answers()
    broken["answers"]["secrecy"]["probabilities"] = {"true": "yes"}
    with pytest.raises(MalformedDecision, match="non-numeric"):
        parse_response(broken, full=True)
    broken = answers()
    del broken["answers"]["scam_type"]["choice"]
    with pytest.raises(MalformedDecision, match="scam_type"):
        parse_response(broken, full=False)


async def test_out_of_range_probabilities_fall_back_to_rules_in_the_engine():
    backend = backend_with(lambda r: httpx.Response(200, json=answers(low=1.7)))
    engine = RiskEngine(decision_backend=backend, decision_timeout_seconds=1)
    transcript = TranscriptWindow()
    transcript.add("caller", "Dzień dobry")
    result = await engine.start_call("CA1", "pl").evaluate(transcript)
    assert result.fallback_reason == "out_of_range"
    assert result.source == "rules"


async def test_unknown_scam_type_is_malformed_in_the_engine():
    backend = backend_with(lambda r: httpx.Response(200, json=answers(choice="aliens")))
    engine = RiskEngine(decision_backend=backend, decision_timeout_seconds=1)
    transcript = TranscriptWindow()
    transcript.add("caller", "Dzień dobry")
    result = await engine.start_call("CA1", "pl").evaluate(transcript)
    assert result.fallback_reason == "malformed_response"
