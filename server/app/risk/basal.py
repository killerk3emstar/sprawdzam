"""basal-1 client (`POST /v1/systemone` of basal-serve).

Question schemas (`schemas/basal_{pl,en}.json`) come from the model bench. Quick requests ask
`risk` + `scam_type` (~1.1 s on the M4 Pro), full requests all six questions (~2 s).

Mapping to our normalised result (team decision, see bench README):
* risk = 100 * (1 - P(low)) from the `risk` score question ("risk not low"); the expected
  level hardly ever reaches "critical", so it would never cross the hang-up threshold;
* scam_type = the `choice` of `scam_type`;
* money / secrecy / authority / urgency = P(true) of the yes/no questions (full only).

Range checks happen in the engine (`DecisionResult`); this client only checks the shape.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

import httpx

from app.config import Lang
from app.risk.decision import (
    SIGNALS,
    DecisionBackendError,
    DecisionRequest,
    MalformedDecision,
)

SCHEMA_DIR = Path(__file__).parent / "schemas"
QUICK_QUESTIONS = ("risk", "scam_type")
MAX_STATE_CHARS = 6000


@cache
def load_schema(lang: Lang) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / f"basal_{lang}.json").read_text(encoding="utf-8"))


def build_questions(lang: Lang, full: bool) -> dict[str, Any]:
    schema = load_schema(lang)
    names = tuple(schema) if full else QUICK_QUESTIONS
    return {name: schema[name] for name in names}


def _probabilities(answers: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    answer = answers.get(name)
    if not isinstance(answer, Mapping):
        raise MalformedDecision(f"missing answer: {name}")
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, Mapping):
        raise MalformedDecision(f"missing probabilities: {name}")
    for value in probabilities.values():
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise MalformedDecision(f"non-numeric probability: {name}")
    return probabilities


def parse_response(payload: Any, full: bool) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("answers"), Mapping):
        raise MalformedDecision("missing answers")
    answers = payload["answers"]
    risk_p = _probabilities(answers, "risk")
    if "low" not in risk_p:
        raise MalformedDecision("risk without P(low)")
    scam = answers.get("scam_type")
    if not isinstance(scam, Mapping) or not isinstance(scam.get("choice"), str):
        raise MalformedDecision("missing scam_type choice")
    result: dict[str, Any] = {
        "risk": 100.0 * (1.0 - float(risk_p["low"])),
        "scam_type": scam["choice"],
    }
    if full:
        for name in SIGNALS:
            probabilities = _probabilities(answers, name)
            if "true" not in probabilities:
                raise MalformedDecision(f"{name} without P(true)")
            result[name] = float(probabilities["true"])
    return result


class BasalBackend:
    name = "basal"

    def __init__(
        self, url: str, timeout: float = 3.0, client: httpx.AsyncClient | None = None
    ) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self.last_latency_ms: float | None = None

    async def assess(self, request: DecisionRequest) -> dict[str, Any]:
        body = {
            "state": request.state[-MAX_STATE_CHARS:],
            "questions": build_questions(request.lang, request.full),
        }
        started = time.perf_counter()
        try:
            response = await self._client.post(
                f"{self.url}/v1/systemone", json=body, timeout=self.timeout
            )
        except httpx.TimeoutException as exc:
            raise DecisionBackendError("timeout") from exc
        except httpx.HTTPError as exc:
            raise DecisionBackendError(f"transport error: {type(exc).__name__}") from exc
        self.last_latency_ms = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            detail = ""
            try:
                error = response.json().get("error")
                detail = f": {str(error)[:120]}" if error else ""
            except (ValueError, AttributeError):
                pass
            raise DecisionBackendError(f"HTTP {response.status_code}{detail}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MalformedDecision("invalid JSON") from exc
        return parse_response(payload, request.full)

    async def warm_up(self) -> float:
        """First decision after start compiles kernels (~2 s); do it before the first call."""
        started = time.perf_counter()
        await self.assess(
            DecisionRequest(call_id="warmup", lang="pl", state="Dzwoniący: Dzień dobry.")
        )
        return (time.perf_counter() - started) * 1000

    async def aclose(self) -> None:
        await self._client.aclose()
