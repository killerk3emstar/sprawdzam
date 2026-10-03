"""REST actions that can spend provider money.

`CallActions` is implemented by every `TelephonyProvider` (Twilio REST for now). It must only
be called through `GuardedCallActions` (see `guard.py`); `build_call_actions` in
`app/factory.py` always wraps it. Return values are informational.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.config import Lang


@runtime_checkable
class CallActions(Protocol):
    async def hang_up(self, call_sid: str) -> object:
        """End the incoming call through the provider REST API (backup to closing the stream)."""
        ...

    async def call_trusted_person(
        self, call_sid: str, to: str, message: str, lang: Lang = "pl"
    ) -> object:
        """Outbound call to the trusted person that speaks `message` (costs money)."""
        ...

    async def send_sms(self, call_sid: str, to: str, body: str) -> object:
        """SMS to the trusted person (costs money)."""
        ...
