"""Risk engine: decision model + keyword rules -> score -> escalating actions.

Scoring (team decision, see the model bench):
* model score = 100 * (1 - P(low)) of basal's `risk` question; combined = max(model, rules);
* warn when the combined score is >= RISK_WARN for two readings in a row;
* verify the family password (then hang up) only when the MODEL's own score is >= RISK_HANGUP
  for two readings in a row AND (the model's cached `secrecy` >= SECRECY_HANGUP_MIN OR a
  keyword-rule hit). The keyword rules do not understand negation ("a bank never asks for
  BLIK"), so on their own they may warn but never hang up: when the model is unavailable
  (source "rules") the engine reaches at most WARN, and a reading without a model answer
  breaks the model's hang-up streak.

Two-tier model questions: every evaluation asks only `risk` + `scam_type`; the first
evaluation after a reading at or above the warn threshold asks all six questions once and
caches money / secrecy / authority / urgency for the alert summary and the hang-up condition.
Optionally (DECISION_FULL_REFRESH_SECONDS > 0) the full set is asked again while the hang-up
gate is blocked only by a stale secrecy answer.

Failure policy: the decision model is optional. On a timeout, HTTP error, malformed or
out-of-range answer the engine logs a structured warning and continues with the rules only.
Nothing here ever raises into the call pipeline because of the model.

Privacy: logs carry the call id, scores, categories and the fallback reason only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.config import Lang
from app.logging_setup import log_event
from app.risk.decision import (
    SIGNALS,
    DecisionBackend,
    DecisionBackendError,
    DecisionRequest,
    DecisionResult,
    MalformedDecision,
)
from app.risk.models import Action, ActionLevel, Category, ScamType
from app.risk.rules import RulesResult, score_text
from app.risk.smoothing import ScoreSmoother
from app.transcript import TranscriptWindow

logger = logging.getLogger(__name__)

_RANGE_ERROR_TYPES = {"less_than_equal", "greater_than_equal", "finite_number"}
MAX_FULL_ATTEMPTS = 2


class ActionHandler(Protocol):
    """Called after every assessment; `assessment.action` is set when a new action fires."""

    async def handle(self, assessment: RiskAssessment) -> None: ...


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
    # Cached model probabilities from the one full request (empty until it ran).
    signals: dict[str, float] = field(default_factory=dict)
    rule_hit: bool = False
    full_request: bool = False


class RiskEngine:
    def __init__(
        self,
        *,
        warn_threshold: int = 50,
        hangup_threshold: int = 90,
        secrecy_hangup_min: float = 0.8,
        decision_backend: DecisionBackend | None = None,
        decision_timeout_seconds: float = 3.0,
        smoothing_window: int = 2,
        confirmations: int = 2,
        full_refresh_seconds: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 <= warn_threshold < hangup_threshold <= 100:
            raise ValueError("expected 0 <= warn_threshold < hangup_threshold <= 100")
        self.warn_threshold = warn_threshold
        self.hangup_threshold = hangup_threshold
        self.secrecy_hangup_min = secrecy_hangup_min
        self.decision_backend = decision_backend
        self.decision_timeout_seconds = decision_timeout_seconds
        self.smoothing_window = smoothing_window
        self.confirmations = confirmations
        # 0 = the full question set is asked once per call (team decision). > 0: ask it again
        # (at most this often) while the hang-up gate is blocked only by a stale secrecy
        # answer, so secrecy said later in the call is still seen by the model.
        self.full_refresh_seconds = full_refresh_seconds
        self.clock = clock

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
        detail: list[dict[str, object]] | str | None = None
        started = time.perf_counter()
        try:
            raw = await asyncio.wait_for(backend.assess(request), self.decision_timeout_seconds)
            result = DecisionResult.model_validate(raw)
            log_event(
                logger,
                logging.INFO,
                "decision_latency",
                call_id=request.call_id,
                backend=getattr(backend, "name", "?"),
                full=request.full,
                ms=round((time.perf_counter() - started) * 1000),
            )
            return result, None
        except TimeoutError:
            reason = "timeout"
        except MalformedDecision as exc:
            reason, error_type, detail = "malformed_response", type(exc).__name__, str(exc)
        except (httpx.HTTPError, DecisionBackendError) as exc:
            reason, error_type = "http_error", type(exc).__name__
            detail = str(exc)[:160] if isinstance(exc, DecisionBackendError) else None
            if detail == "timeout":
                reason = "timeout"
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
            full=request.full,
            reason=reason,
            error_type=error_type,
            errors=detail,
            ms=round((time.perf_counter() - started) * 1000),
        )
        return None, reason


class CallRiskMonitor:
    """Per-call risk state: smoothing history, cached full answers, highest action taken."""

    def __init__(
        self, engine: RiskEngine, call_id: str, lang: Lang, handler: ActionHandler | None
    ) -> None:
        self.engine = engine
        self.call_id = call_id
        self.lang = lang
        self.handler = handler
        self.smoother = ScoreSmoother(engine.smoothing_window, engine.confirmations)
        # The model's own readings (0 when it did not answer): only these can reach hang-up.
        self.model_smoother = ScoreSmoother(engine.smoothing_window, engine.confirmations)
        self.highest = Action.NONE
        self.signals: dict[str, float] = {}
        self._full_attempts = 0
        self._last_raw: int | None = None
        self._last_full_at: float | None = None
        self._gate_blocked = False  # >= hangup twice, but no secrecy and no rule hit

    def _want_full(self) -> bool:
        engine = self.engine
        if engine.decision_backend is None or self._last_raw is None:
            return False
        if not self.signals:
            return (
                self._full_attempts < MAX_FULL_ATTEMPTS and self._last_raw >= engine.warn_threshold
            )
        return (
            engine.full_refresh_seconds > 0
            and self._gate_blocked
            and self._last_full_at is not None
            and engine.clock() - self._last_full_at >= engine.full_refresh_seconds
        )

    def _level(self, rule_hit: bool) -> Action:
        engine = self.engine
        secrecy = self.signals.get("secrecy", 0.0)
        if self.model_smoother.sustained(engine.hangup_threshold) and (
            secrecy >= engine.secrecy_hangup_min or rule_hit
        ):
            return Action.VERIFY_THEN_HANGUP
        if self.smoother.sustained(engine.warn_threshold):
            return Action.WARN
        return Action.NONE

    def _rule_hit(self, rules: RulesResult) -> bool:
        """Keyword rules on their own point at a scam: a secrecy phrase, or a combination of
        signs reaching the warn threshold."""
        return Category.SECRECY in rules.categories or rules.score >= self.engine.warn_threshold

    async def evaluate(self, transcript: TranscriptWindow) -> RiskAssessment:
        rules = score_text(transcript.text(), self.lang)
        full = self._want_full()
        if full:
            self._full_attempts += 1
            self._last_full_at = self.engine.clock()
        model, fallback_reason = await self.engine.run_decision(
            DecisionRequest(
                call_id=self.call_id,
                lang=self.lang,
                state=transcript.render(self.lang),
                full=full,
            )
        )
        if model is not None and full and model.has_signals:
            self.signals = {name: float(getattr(model, name)) for name in SIGNALS}
        raw = combine_scores(rules, model)
        self._last_raw = raw
        smoothed = self.smoother.update(raw)
        self.model_smoother.update(0.0 if model is None else model.risk)
        rule_hit = self._rule_hit(rules)
        level = self._level(rule_hit)
        self._gate_blocked = (
            self.model_smoother.sustained(self.engine.hangup_threshold)
            and level is not Action.VERIFY_THEN_HANGUP
        )
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
            categories=combine_categories(rules, self.signals),
            signals=dict(self.signals),
            rule_hit=rule_hit,
            full_request=full,
        )
        log_event(
            logger,
            logging.INFO,
            "risk_assessment",
            call_id=self.call_id,
            source=assessment.source,
            fallback_reason=fallback_reason,
            full_request=full,
            rules_score=rules.score,
            model_score=None if model is None else round(model.risk),
            raw_score=raw,
            smoothed_score=assessment.smoothed_score,
            level=level.value,
            action=action.value,
            scam_type=assessment.scam_type.value,
            categories=[name for name, on in assessment.categories.items() if on],
            signals={k: round(v, 2) for k, v in self.signals.items()},
            rule_hit=rule_hit,
        )
        if self.handler is not None:
            try:
                await self.handler.handle(assessment)
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


def combine_categories(rules: RulesResult, signals: dict[str, float]) -> dict[str, bool]:
    flags = rules.flags()
    for category in Category:
        flags[category.value] = flags[category.value] or signals.get(category.value, 0.0) >= 0.5
    return flags
