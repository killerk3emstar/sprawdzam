"""Admission control for incoming calls: concurrency limit, stream tokens, rate limit.

`CallAdmission` ties the `/twilio/voice` webhook to the Media Stream WebSocket:

* The voice webhook calls `admit(call_sid)`. If fewer than `max_concurrent` calls are pending
  or active, it returns a one-time token (valid `token_ttl` seconds) that goes into the TwiML
  `<Parameter name="token">`. Otherwise the caller hears "protection unavailable".
* The WebSocket `start` message must carry that token with the same CallSid; `activate`
  consumes it. A stream without a valid token, or beyond the limit, is refused.
* `release` frees the slot when the stream ends.

Everything is in memory: a restart drops pending tokens, so streams in flight are refused
and Twilio ends those calls (the caller can ring again).
"""

from __future__ import annotations

import hmac
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from app.config import Lang


@dataclass
class Admission:
    call_sid: str
    token: str
    expires_at: float
    caller: str = ""  # RAM only, shown masked to the senior, never logged
    lang: Lang = "pl"


class CallAdmission:
    def __init__(
        self,
        max_concurrent: int,
        token_ttl: float = 120.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self.max_concurrent = max_concurrent
        self.token_ttl = token_ttl
        self._clock = clock
        self._pending: dict[str, Admission] = {}  # call_sid -> pending admission
        self._active: set[str] = set()

    def _purge(self) -> None:
        now = self._clock()
        for sid in [sid for sid, p in self._pending.items() if p.expires_at <= now]:
            del self._pending[sid]

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def pending_count(self) -> int:
        self._purge()
        return len(self._pending)

    def admit(self, call_sid: str, caller: str = "", lang: Lang = "pl") -> str | None:
        """Reserve a slot for `call_sid` and return its stream token, or None when full."""
        self._purge()
        if call_sid in self._active:
            return None  # a second webhook for a call that already streams
        existing = self._pending.get(call_sid)
        if existing is None and len(self._pending) + len(self._active) >= self.max_concurrent:
            return None
        token = secrets.token_urlsafe(24)
        # A Twilio retry for the same CallSid replaces its token instead of taking a new slot.
        self._pending[call_sid] = Admission(
            call_sid, token, self._clock() + self.token_ttl, caller, lang
        )
        return token

    def activate(self, call_sid: str, token: str) -> Admission | None:
        """Consume the token for `call_sid`. Returns the admission if the stream may proceed."""
        self._purge()
        pending = self._pending.get(call_sid)
        if pending is None or not token or not hmac.compare_digest(pending.token, token):
            return None
        del self._pending[call_sid]
        if len(self._active) >= self.max_concurrent:
            return None
        self._active.add(call_sid)
        return pending

    def release(self, call_sid: str) -> None:
        self._active.discard(call_sid)
        self._pending.pop(call_sid, None)


class SlidingWindowRateLimiter:
    """At most `limit` events per `window` seconds (global, in memory)."""

    def __init__(
        self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self.limit = limit
        self.window = window
        self._clock = clock
        self._events: deque[float] = deque()

    def allow(self) -> bool:
        now = self._clock()
        while self._events and self._events[0] <= now - self.window:
            self._events.popleft()
        if len(self._events) >= self.limit:
            return False
        self._events.append(now)
        return True
