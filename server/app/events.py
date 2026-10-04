"""In-process pub/sub of live call events for the jury / operator console (`WS /dev/events`).

Event schema (server -> page JSON, stable; fields are only ever added):

* `hello`        {warn, hangup, alerts: [<alert>...]}               (on subscribe)
* `call_started` {callId, at, caller, lang}
* `transcript`   {callId, at, speaker: "caller"|"senior", text}
* `risk`         {callId, at, score, modelScore, rulesScore, level, scamType, reasons, source}
* `action`       {callId, at, action, detail}
* `call_ended`   {callId, at, reason, alert: <alert>|null}
* `<alert>`      {callId, at, caller, scamType, maxScore, outcome: warned|blocked|normal, actions}

`at` is ISO 8601 UTC with milliseconds. Alerts never contain transcript text; the last 50
are kept in RAM only (`GET /dev/alerts`). Transcript events exist only on this live stream:
they are never stored or logged.

Publishing is synchronous and never blocks: every subscriber has a bounded queue and the
oldest event is dropped when a slow or dead page falls behind, so the call pipeline is never
slowed down by a viewer.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.logging_setup import log_event

logger = logging.getLogger(__name__)

SUBSCRIBER_QUEUE = 256
MAX_ALERTS = 50
MAX_OPEN_CALLS = 100

ACTIONS = frozenset(
    {
        "warn",
        "verify_password",
        "password_ok",
        "password_failed",
        "hangup",
        "sms_requested",
        "sms_sent",
        "sms_failed",
        "fail_open",
    }
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class _CallRecord:
    caller: str
    analysed: bool = True
    max_score: int = 0
    scam_type: str = "none"
    warned: bool = False
    risk_readings: int = 0
    actions: list[str] = field(default_factory=list)


class Subscription:
    def __init__(self, bus: EventBus, size: int) -> None:
        self._bus = bus
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=size)
        self.dropped = 0

    def push(self, event: dict[str, Any]) -> None:
        if self.queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            self.dropped += 1
        self.queue.put_nowait(event)

    async def get(self) -> dict[str, Any]:
        return await self.queue.get()

    def close(self) -> None:
        self._bus.unsubscribe(self)


class EventBus:
    def __init__(self, warn: int = 50, hangup: int = 90, queue_size: int = SUBSCRIBER_QUEUE):
        self.warn = warn
        self.hangup = hangup
        self.queue_size = queue_size
        self._subscribers: set[Subscription] = set()
        self._calls: dict[str, _CallRecord] = {}
        self.alerts: deque[dict[str, Any]] = deque(maxlen=MAX_ALERTS)

    # ------------------------------------------------------------------ subscribers
    def subscribe(self) -> Subscription:
        sub = Subscription(self, self.queue_size)
        self._subscribers.add(sub)
        sub.push(self.hello())
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._subscribers.discard(sub)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def hello(self) -> dict[str, Any]:
        return {
            "type": "hello",
            "warn": self.warn,
            "hangup": self.hangup,
            "alerts": list(self.alerts),
        }

    def alert_list(self) -> list[dict[str, Any]]:
        return list(self.alerts)

    def _publish(self, event: dict[str, Any]) -> None:
        for sub in list(self._subscribers):
            try:
                sub.push(event)
            except Exception as exc:  # noqa: BLE001 - a viewer must never break a call
                log_event(
                    logger, logging.WARNING, "event_push_failed", error_type=type(exc).__name__
                )

    # ------------------------------------------------------------------ publishers
    def call_started(self, call_id: str, caller: str, lang: str, analysed: bool = True) -> None:
        if len(self._calls) >= MAX_OPEN_CALLS:  # leak guard; calls normally end
            self._calls.pop(next(iter(self._calls)))
        self._calls[call_id] = _CallRecord(caller=caller, analysed=analysed)
        self._publish(
            {
                "type": "call_started",
                "callId": call_id,
                "at": now_iso(),
                "caller": caller,
                "lang": lang,
            }
        )

    def transcript(self, call_id: str, speaker: str, text: str) -> None:
        self._publish(
            {
                "type": "transcript",
                "callId": call_id,
                "at": now_iso(),
                "speaker": speaker,
                "text": text,
            }
        )

    def risk(
        self,
        call_id: str,
        *,
        score: int,
        model_score: int | None,
        rules_score: int,
        level: str,
        scam_type: str,
        reasons: list[str],
        source: str,
    ) -> None:
        record = self._calls.get(call_id)
        if record is not None:
            record.risk_readings += 1
            record.max_score = max(record.max_score, score)
            if scam_type != "none":
                record.scam_type = scam_type
            if level in ("warn", "high"):
                record.warned = True
        self._publish(
            {
                "type": "risk",
                "callId": call_id,
                "at": now_iso(),
                "score": score,
                "modelScore": model_score,
                "rulesScore": rules_score,
                "level": level,
                "scamType": scam_type,
                "reasons": reasons,
                "source": source,
            }
        )

    def action(self, call_id: str, action: str, detail: str = "") -> None:
        record = self._calls.get(call_id)
        if record is not None:
            record.actions.append(action)
        else:  # after the call ended (e.g. the SMS result): update the stored alert
            for alert in self.alerts:
                if alert["callId"] == call_id:
                    alert["actions"].append(action)
                    break
        self._publish(
            {
                "type": "action",
                "callId": call_id,
                "at": now_iso(),
                "action": action,
                "detail": detail,
            }
        )

    def call_ended(self, call_id: str, reason: str) -> dict[str, Any] | None:
        record = self._calls.pop(call_id, None)
        alert = None
        if record is not None and record.analysed and record.risk_readings:
            if reason == "scam_blocked":
                outcome = "blocked"
            elif record.warned:
                outcome = "warned"
            else:
                outcome = "normal"
            alert = {
                "callId": call_id,
                "at": now_iso(),
                "caller": record.caller,
                "scamType": record.scam_type,
                "maxScore": record.max_score,
                "outcome": outcome,
                "actions": list(record.actions),
            }
            self.alerts.append(alert)
        self._publish(
            {
                "type": "call_ended",
                "callId": call_id,
                "at": now_iso(),
                "reason": reason,
                "alert": alert,
            }
        )
        return alert
