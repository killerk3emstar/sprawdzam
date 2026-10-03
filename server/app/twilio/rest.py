"""Minimal async Twilio REST client (hang up, outbound call, SMS) on httpx.

Only ever used through `GuardedCallActions` (dry run, allowlist, caps). Credentials: an API
key (TWILIO_API_KEY_SID/SECRET) if set, otherwise the account SID and auth token.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import Settings

API_BASE = "https://api.twilio.com/2010-04-01"
CALL_SID_RE = re.compile(r"^CA[0-9a-f]{32}$")


class ProviderNotConfigured(RuntimeError):
    pass


class TwilioRest:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.settings = settings
        self._client = client
        self.timeout = timeout

    def _credentials(self) -> tuple[str, str, str]:
        s = self.settings
        account = s.TWILIO_ACCOUNT_SID
        if s.TWILIO_API_KEY_SID and s.TWILIO_API_KEY_SECRET.get_secret_value():
            user, password = s.TWILIO_API_KEY_SID, s.TWILIO_API_KEY_SECRET.get_secret_value()
        else:
            user, password = account, s.twilio_auth_token
        if not account or not user or not password:
            raise ProviderNotConfigured("Twilio account SID and credentials are required")
        return account, user, password

    async def _post(self, path: str, data: dict[str, str]) -> dict[str, Any]:
        account, user, password = self._credentials()
        url = f"{API_BASE}/Accounts/{account}/{path}"
        if self._client is not None:
            response = await self._client.post(url, data=data, auth=(user, password))
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, data=data, auth=(user, password))
        response.raise_for_status()
        return response.json()

    def _from_number(self) -> str:
        if not self.settings.TWILIO_NUMBER:
            raise ProviderNotConfigured("TWILIO_NUMBER is required for outbound calls and SMS")
        return self.settings.TWILIO_NUMBER

    async def hang_up(self, call_sid: str) -> dict[str, Any]:
        if not CALL_SID_RE.fullmatch(call_sid):
            raise ValueError("invalid CallSid")
        return await self._post(f"Calls/{call_sid}.json", {"Status": "completed"})

    async def create_call(self, to: str, twiml: str) -> dict[str, Any]:
        return await self._post(
            "Calls.json", {"To": to, "From": self._from_number(), "Twiml": twiml}
        )

    async def send_sms(self, to: str, body: str) -> dict[str, Any]:
        return await self._post(
            "Messages.json", {"To": to, "From": self._from_number(), "Body": body}
        )
