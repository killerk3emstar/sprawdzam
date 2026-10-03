"""Risk engine: decision model + keyword rules -> smoothed score -> escalating actions.

Failure policy: the decision model is optional. On a timeout, HTTP error, malformed or
out-of-range answer the engine logs a structured warning and continues with the rules only.
Nothing here ever raises into the call pipeline because of the model.

Privacy: logs carry the call id, scores, categories and the fallback reason only.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.config import Lang
from app.logging_setup import log_event
from app.risk.decision import (
    DecisionBackend,
    DecisionBackendError,
    DecisionRequest,
    DecisionResult,
)
from app.risk.models import Action, ActionLevel, Category, ScamType
from app.risk.rules import RulesResult, score_text
from app.risk.smoothing import ScoreSmoother
from app.transcript import TranscriptWindow

logger = logging.getLogger(__name__)

_RANGE_ERROR_TYPES = {"less_than_equal", "greater_than_equal", "finite_number"}


class ActionHandler(Protocol):
    async def handle(self, call_id: str, action: Action, assessment: RiskAssessment) -> None: ...


@dataclass(frozen=True)
class RiskAssessment:
    call_id: str
    rules: RulesResult
    model: DecisionResult | None
    source: str  # "model+rules" | "rules"
    fallback_reason: str | None  # None, "not_configured", "timeout", "http_error", ...
    raw_score: int
    smoothed_score: int
    level: Action  # what the thresholds say right now
    action: Action  # newly triggered action (escalation only), Action.NONE otherwise
    scam_type: ScamType
    categories: dict[str, bool] = field(default_factory=dict)


class RiskEngine:
    def __init__(
        self,
        *,
        warn_threshold: int = 50,
        hangup_threshold: int = 80,
        decision_backend: DecisionBackend | None = None,
        decision_timeout_seconds: float = 2.0,
        smoothing_window: int = 2,
        hangup_confirmations: int = 2,
    ) -> None:
        if not 0 <= warn_threshold < hangup_threshold <= 100:
            raise ValueError("expected 0 <= warn_threshold < hangup_threshold <= 100")
        self.warn_threshold = warn_threshold
        self.hangup_threshold = hangup_threshold
        self.decision_backend = decision_backend
        self.decision_timeout_seconds = decision_timeout_seconds
        self.smoothing_window = smoothing_window
        self.hangup_confirmations = hangup_confirmations

    def start_call(
        self, call_id: str, lang: Lang, handler: ActionHandler | None = None
    ) -> CallRiskMonitor:
        return CallRiskMonitor(self, call_id, lang, handler)

    async def run_decision(
        self, request: DecisionRequest
    ) -> tuple[DecisionResult | None, str | None]:
        """Ask the decision backend. Returns (result, fallback_reason)."""
        backend = self.decision_backend
        if backend is None:
            return None, "not_configured"
        reason: str
        error_type: str | None = None
        detail: list[dict[str, object]] | None = None
        try:
            raw = await asyncio.wait_for(backend.assess(request), self.decision_timeout_seconds)
            return DecisionResult.model_validate(raw), None
        except TimeoutError:
            reason = "timeout"
        except (httpx.HTTPError, DecisionBackendError) as exc:
            reason, error_type = "http_error", type(exc).__name__
        except ValidationError as exc:
            errors = exc.errors(include_input=False, include_url=False)
            range_error = any(e["type"] in _RANGE_ERROR_TYPES for e in errors)
            reason = "out_of_range" if range_error else "malformed_response"
            detail = [{"loc": list(e["loc"]), "type": e["type"]} for e in errors[:5]]
        except Exception as exc:  # noqa: BLE001 - a broken client must never break a call
            reason, error_type = "unexpected_error", type(exc).__name__
        log_event(
            logger,
            logging.WARNING,
            "decision_fallback_to_rules",
            call_id=request.call_id,
            backend=getattr(backend, "name", type(backend).__name__),
            reason=reason,
            error_type=error_type,
            errors=detail,
        )
        return None, reason


class CallRiskMonitor:
    """Per-call risk state: smoothing history and the highest action already taken."""

    def __init__(
        self, engine: RiskEngine, call_id: str, lang: Lang, handler: ActionHandler | None
    ) -> None:
        self.engine = engine
        self.call_id = call_id
        self.lang = lang
        self.handler = handler
        self.smoother = ScoreSmoother(engine.smoothing_window, engine.hangup_confirmations)
        self.highest = Action.NONE

    def _level(self) -> Action:
        if self.smoother.sustained(self.engine.hangup_threshold):
            return Action.VERIFY_THEN_HANGUP
        if self.smoother.smoothed >= self.engine.warn_threshold:
            return Action.WARN
        return Action.NONE

    async def evaluate(self, transcript: TranscriptWindow) -> RiskAssessment:
        rules = score_text(transcript.text(), self.lang)
        model, fallback_reason = await self.engine.run_decision(
            DecisionRequest(call_id=self.call_id, lang=self.lang, state=transcript.render())
        )
        raw = combine_scores(rules, model)
        smoothed = self.smoother.update(raw)
        level = self._level()
        action = Action.NONE
        if ActionLevel.of(level) > ActionLevel.of(self.highest):
            action = level
            self.highest = level

        assessment = RiskAssessment(
            call_id=self.call_id,
            rules=rules,
            model=model,
            source="model+rules" if model is not None else "rules",
            fallback_reason=fallback_reason,
            raw_score=raw,
            smoothed_score=round(smoothed),
            level=level,
            action=action,
            scam_type=combine_scam_type(rules, model),
            categories=combine_categories(rules, model),
        )
        log_event(
            logger,
            logging.INFO,
            "risk_assessment",
            call_id=self.call_id,
            source=assessment.source,
            fallback_reason=fallback_reason,
            rules_score=rules.score,
            model_score=None if model is None else round(model.risk),
            raw_score=raw,
            smoothed_score=assessment.smoothed_score,
            level=level.value,
            action=action.value,
            scam_type=assessment.scam_type.value,
            categories=[name for name, on in assessment.categories.items() if on],
        )
        if action is not Action.NONE and self.handler is not None:
            try:
                await self.handler.handle(self.call_id, action, assessment)
            except Exception as exc:  # noqa: BLE001 - actions are best effort, call goes on
                log_event(
                    logger,
                    logging.ERROR,
                    "action_failed",
                    call_id=self.call_id,
                    action=action.value,
                    error_type=type(exc).__name__,
                )
        return assessment


def combine_scores(rules: RulesResult, model: DecisionResult | None) -> int:
    """Rules are a safety net: the higher of the two scores wins."""
    if model is None:
        return rules.score
    return max(rules.score, round(model.risk))


def combine_scam_type(rules: RulesResult, model: DecisionResult | None) -> ScamType:
    if model is not None and model.scam_type is not ScamType.NONE:
        return model.scam_type
    return rules.scam_type


def combine_categories(rules: RulesResult, model: DecisionResult | None) -> dict[str, bool]:
    flags = rules.flags()
    if model is not None:
        for category in Category:
            flags[category.value] = flags[category.value] or bool(getattr(model, category.value))
    return flags
