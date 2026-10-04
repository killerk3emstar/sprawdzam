"""Turns engine decisions into call actions (the "what to do" for each risk level).

The alert texts contain the risk score and scam pattern only: no transcript, no caller data.
"""

from __future__ import annotations

import logging
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any, Protocol

from app.config import Lang
from app.logging_setup import log_event
from app.relay.protocol import EndReason
from app.risk.models import Action, ScamType
from app.telephony.actions import CallActions

if TYPE_CHECKING:
    from app.risk.engine import RiskAssessment

logger = logging.getLogger(__name__)

_SCAM_NAMES: dict[Lang, dict[ScamType, str]] = {
    "pl": {
        ScamType.NONE: "nieokreślony",
        ScamType.GRANDCHILD: "„na wnuczka”",
        ScamType.POLICE: "„na policjanta”",
        ScamType.BANK: "„na pracownika banku”",
        ScamType.OTHER: "inne oszustwo",
    },
    "en": {
        ScamType.NONE: "unspecified",
        ScamType.GRANDCHILD: "relative in trouble",
        ScamType.POLICE: "fake police officer",
        ScamType.BANK: "fake bank employee",
        ScamType.OTHER: "other fraud",
    },
}


_SIGNAL_NAMES: dict[Lang, dict[str, str]] = {
    "pl": {
        "money": "pieniądze",
        "secrecy": "tajemnica",
        "authority": "podszywanie się pod urząd",
        "urgency": "presja czasu",
    },
    "en": {
        "money": "money",
        "secrecy": "secrecy",
        "authority": "fake authority",
        "urgency": "time pressure",
    },
}


def _signals(assessment: RiskAssessment, lang: Lang) -> str:
    categories = getattr(assessment, "categories", {}) or {}
    names = [_SIGNAL_NAMES[lang][name] for name, on in categories.items() if on]
    return ", ".join(names)


def alert_sms(assessment: RiskAssessment, lang: Lang) -> str:
    pattern = _SCAM_NAMES[lang][assessment.scam_type]
    score = assessment.smoothed_score
    signals = _signals(assessment, lang)
    if lang == "pl":
        extra = f", sygnały: {signals}" if signals else ""
        return (
            f"Sprawdzam: zatrzymaliśmy podejrzane połączenie do Twojej bliskiej osoby "
            f"(ryzyko {score}/100, wzorzec: {pattern}{extra}). "
            f"Zadzwoń do niej z własnego telefonu."
        )
    extra = f", signals: {signals}" if signals else ""
    return (
        f"Second Ear: we stopped a suspicious call to your relative "
        f"(risk {score}/100, pattern: {pattern}{extra}). Please call them yourself."
    )


def alert_voice(assessment: RiskAssessment, lang: Lang) -> str:
    pattern = _SCAM_NAMES[lang][assessment.scam_type]
    if lang == "pl":
        return (
            "Tu usługa Sprawdzam. Zatrzymaliśmy podejrzane połączenie do Twojej bliskiej "
            f"osoby. Wzorzec: {pattern}. Prosimy, zadzwoń do niej jak najszybciej."
        )
    return (
        "This is Second Ear. We stopped a suspicious call to your relative. "
        f"Pattern: {pattern}. Please call them as soon as possible."
    )


class CallControl(Protocol):
    """What the responder needs from the call (implemented by `CallBridge`)."""

    async def send_risk(self, assessment: RiskAssessment) -> None: ...

    async def play_warning(self) -> None: ...

    async def verify_family_password(self, warn_first: bool = False) -> bool: ...

    async def play_blocked_notice(self) -> None: ...

    async def end(self, reason: EndReason) -> None: ...

    def spawn_background(self, coro: Coroutine[Any, Any, Any]) -> object: ...


class IncidentResponder:
    """Engine `ActionHandler` for one call.

    * every assessment -> `risk` event to the senior's app
    * warn -> spoken warning (or beeps) for the senior
    * high -> family-password check (spoken request to both sides; the senior hears the
      warning first if there was none yet); if it fails: spoken notice to the caller, end the
      call (`scam_blocked`; closing the media stream ends the phone call), REST hang-up as a
      backup, then call and SMS the trusted person. Spending goes through
      `GuardedCallActions`.
    """

    def __init__(
        self, call: CallControl, actions: CallActions, lang: Lang, trusted_number: str = ""
    ) -> None:
        self.call = call
        self.actions = actions
        self.lang = lang
        self.trusted_number = trusted_number
        self.warned = False

    async def handle(self, assessment: RiskAssessment) -> None:
        await self.call.send_risk(assessment)
        if assessment.action is Action.WARN:
            self.warned = True
            await self.call.play_warning()
        elif assessment.action is Action.VERIFY_THEN_HANGUP:
            warn_first = not self.warned
            self.warned = True
            # In the background: the password wait must not stall speech recognition.
            self.call.spawn_background(self.verify_or_block(assessment, warn_first))

    async def verify_or_block(self, assessment: RiskAssessment, warn_first: bool = False) -> None:
        call_id = assessment.call_id
        if await self.call.verify_family_password(warn_first):
            log_event(logger, logging.INFO, "incident_cleared_by_password", call_id=call_id)
            return
        log_event(
            logger,
            logging.WARNING,
            "scam_blocked",
            call_id=call_id,
            score=assessment.smoothed_score,
            scam_type=assessment.scam_type.value,
        )
        # Both are no-ops when the senior already ended the call (hang-up during the stage).
        await self._step("blocked_notice", self.call.play_blocked_notice(), call_id)
        await self._step("end_call", self.call.end(EndReason.SCAM_BLOCKED), call_id)
        await self._follow_up(assessment)

    async def after_senior_block(self) -> None:
        """The senior hung up on a high-risk call before any password / confirm stage."""
        assessment = getattr(self.call, "last_assessment", None)
        if assessment is not None:
            await self._follow_up(assessment)

    async def _follow_up(self, assessment: RiskAssessment) -> None:
        """REST hang-up (backup), then call and SMS the trusted person (all guarded)."""
        call_id = assessment.call_id
        await self._step("hang_up", self.actions.hang_up(call_id), call_id)
        if not self.trusted_number:
            log_event(logger, logging.INFO, "no_trusted_person_configured", call_id=call_id)
            return
        await self._step(
            "call_trusted_person",
            self.actions.call_trusted_person(
                call_id, self.trusted_number, alert_voice(assessment, self.lang), self.lang
            ),
            call_id,
        )
        await self._step(
            "send_sms",
            self.actions.send_sms(call_id, self.trusted_number, alert_sms(assessment, self.lang)),
            call_id,
        )

    async def _step(self, name: str, coro: Coroutine[Any, Any, Any], call_id: str) -> None:
        # One failing step must not stop the others (e.g. SMS still goes out if hang-up fails).
        try:
            await coro
        except Exception as exc:  # noqa: BLE001
            log_event(
                logger,
                logging.ERROR,
                "incident_step_failed",
                call_id=call_id,
                step=name,
                error_type=type(exc).__name__,
            )
