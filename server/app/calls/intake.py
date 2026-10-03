"""Shared admission step for a new incoming call (voice webhook and the dev caller page)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from app.config import Lang
from app.logging_setup import log_event
from app.services import Services

logger = logging.getLogger(__name__)


class AdmitOutcome(StrEnum):
    ADMITTED = "admitted"
    NO_APP = "no_app"  # no senior app control channel open: protection unavailable
    CAPACITY = "capacity"  # MAX_CONCURRENT_CALLS reached


@dataclass(frozen=True)
class AdmitResult:
    outcome: AdmitOutcome
    token: str | None = None


def admit_call(services: Services, call_id: str, caller: str, lang: Lang) -> AdmitResult:
    if not services.hub.online:
        log_event(
            logger,
            logging.WARNING,
            "incoming_call_rejected",
            call_id=call_id,
            reason=AdmitOutcome.NO_APP.value,
        )
        return AdmitResult(AdmitOutcome.NO_APP)
    token = services.admission.admit(call_id, caller=caller, lang=lang)
    if token is None:
        log_event(
            logger,
            logging.WARNING,
            "incoming_call_rejected",
            call_id=call_id,
            reason=AdmitOutcome.CAPACITY.value,
            max_concurrent=services.settings.MAX_CONCURRENT_CALLS,
        )
        return AdmitResult(AdmitOutcome.CAPACITY)
    log_event(logger, logging.INFO, "incoming_call_accepted", call_id=call_id, lang=lang)
    return AdmitResult(AdmitOutcome.ADMITTED, token)
