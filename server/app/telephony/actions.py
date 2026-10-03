"""Side effects the risk engine can trigger during a call.

`CallActions` is the only way the engine reaches the outside world. Anything that can spend
Twilio money (`hang_up` via REST, `call_trusted_person`, `send_sms`) must be wrapped in
`GuardedCallActions` (see `guard.py`); `build_call_actions` in `app/factory.py` always does it.

Return values are informational (the guard returns a `GuardOutcome`).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.logging_setup import log_event

if TYPE_CHECKING:
    from app.risk.engine import RiskAssessment

logger = logging.getLogger(__name__)


@runtime_checkable
class CallActions(Protocol):
    async def warn(self, call_sid: str, assessment: RiskAssessment) -> object:
        """Voice warning in the call and an alert in the senior's app (no Twilio spend)."""
        ...

    async def hang_up(self, call_sid: str) -> object:
        """End the incoming call (Twilio REST)."""
        ...

    async def call_trusted_person(self, call_sid: str, to: str, message: str) -> object:
        """Outbound call to the trusted person that speaks `message` (Twilio, costs money)."""
        ...

    async def send_sms(self, call_sid: str, to: str, body: str) -> object:
        """SMS to the trusted person (Twilio, costs money)."""
        ...


class LoggingCallActions:
    """Placeholder until the Twilio REST implementation exists: logs and does nothing."""

    async def warn(self, call_sid: str, assessment: RiskAssessment) -> None:
        log_event(logger, logging.INFO, "action_warn_not_implemented", call_id=call_sid)

    async def hang_up(self, call_sid: str) -> None:
        log_event(logger, logging.INFO, "action_hang_up_not_implemented", call_id=call_sid)

    async def call_trusted_person(self, call_sid: str, to: str, message: str) -> None:
        log_event(logger, logging.INFO, "action_call_not_implemented", call_id=call_sid)

    async def send_sms(self, call_sid: str, to: str, body: str) -> None:
        log_event(logger, logging.INFO, "action_sms_not_implemented", call_id=call_sid)
