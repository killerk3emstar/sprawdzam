"""Cost and safety guard around `CallActions`.

Even a buggy engine, a runaway loop or a test pointed at the real Twilio account must not be
able to run up a bill or call strangers. Every money-spending action passes these checks:

1. Dry run (`TELEPHONY_DRY_RUN`, default true): log "would do X", execute nothing.
2. Destination checks: valid E.164, never our own `TWILIO_NUMBER` (call loops), and only
   numbers on `OUTBOUND_ALLOWLIST`.
3. Per-incident dedupe: at most one REST hang-up, one trusted-person call and one SMS per
   incoming call, however many high-risk readings arrive.
4. Daily caps (`MAX_OUTBOUND_CALLS_PER_DAY`, `MAX_SMS_PER_DAY`), persisted in a small JSON
   file (date + counts only, no numbers or content) so a restart does not reset them. The
   counter is reserved *before* the action runs, so a crash cannot lose a spend. If the file
   cannot be read or written, outbound actions are refused (fail closed for spending).

Checks run in the order: number validation -> own number -> allowlist -> dedupe -> dry run
-> daily cap -> execute. Dry-run actions do not count against the caps.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.config import Lang
from app.logging_setup import log_event
from app.telephony.actions import CallActions
from app.telephony.numbers import is_e164, mask_number

logger = logging.getLogger(__name__)

CounterKind = Literal["calls", "sms"]


class GuardOutcome(StrEnum):
    EXECUTED = "executed"
    DRY_RUN = "dry_run"
    DUPLICATE = "duplicate"
    REFUSED_INVALID_NUMBER = "refused_invalid_number"
    REFUSED_OWN_NUMBER = "refused_own_number"
    REFUSED_NOT_ALLOWLISTED = "refused_not_allowlisted"
    REFUSED_DAILY_CAP = "refused_daily_cap"
    REFUSED_COUNTER_ERROR = "refused_counter_error"
    FAILED = "failed"


class CounterStoreError(Exception):
    """The persisted counter file is unreadable or cannot be written."""


class _CounterFile(BaseModel):
    date: date
    calls: int = Field(default=0, ge=0)
    sms: int = Field(default=0, ge=0)


def utc_today() -> date:
    return datetime.now(UTC).date()


class DailyCounterStore:
    """Daily outbound counters persisted as JSON (UTC day). Single-process use."""

    FILENAME = "telephony_counters.json"

    def __init__(self, data_dir: Path | str, today: Callable[[], date] = utc_today) -> None:
        self.path = Path(data_dir) / self.FILENAME
        self._today = today

    def _load(self) -> _CounterFile:
        today = self._today()
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _CounterFile(date=today)
        except OSError as exc:
            raise CounterStoreError(f"cannot read counters: {type(exc).__name__}") from exc
        try:
            data = _CounterFile.model_validate(json.loads(raw))
        except (ValueError, ValidationError) as exc:
            raise CounterStoreError("counter file is corrupt") from exc
        return data if data.date == today else _CounterFile(date=today)

    def _save(self, data: _CounterFile) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".counters-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(data.model_dump_json())
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise CounterStoreError(f"cannot write counters: {type(exc).__name__}") from exc

    def counts(self) -> dict[str, int]:
        data = self._load()
        return {"calls": data.calls, "sms": data.sms}

    def try_reserve(self, kind: CounterKind, cap: int) -> bool:
        """Increment `kind` if it is below `cap`. Returns False when the cap is reached."""
        data = self._load()
        current = getattr(data, kind)
        if current >= cap:
            return False
        self._save(data.model_copy(update={kind: current + 1}))
        return True


@dataclass(frozen=True)
class GuardConfig:
    dry_run: bool = True
    allowlist: frozenset[str] = frozenset()
    own_number: str = ""
    max_calls_per_day: int = 10
    max_sms_per_day: int = 20
    dedupe_memory: int = 1000


class GuardedCallActions:
    """`CallActions` wrapper enforcing dry run, allowlist, dedupe and daily caps."""

    def __init__(self, inner: CallActions, config: GuardConfig, counters: DailyCounterStore):
        self.inner = inner
        self.config = config
        self.counters = counters
        # call_sid -> kinds of actions already done (bounded, oldest calls forgotten first).
        self._done: OrderedDict[str, set[str]] = OrderedDict()

    # ------------------------------------------------------------------ public API
    async def hang_up(self, call_sid: str) -> GuardOutcome:
        if self._seen(call_sid, "hang_up"):
            return self._log(GuardOutcome.DUPLICATE, "hang_up", call_sid)
        self._mark(call_sid, "hang_up")
        if self.config.dry_run:
            return self._log(GuardOutcome.DRY_RUN, "hang_up", call_sid)
        return await self._run("hang_up", call_sid, self.inner.hang_up(call_sid))

    async def call_trusted_person(
        self, call_sid: str, to: str, message: str, lang: Lang = "pl"
    ) -> GuardOutcome:
        return await self._outbound(
            "call",
            "calls",
            self.config.max_calls_per_day,
            call_sid,
            to,
            lambda: self.inner.call_trusted_person(call_sid, to, message, lang),
        )

    async def send_sms(self, call_sid: str, to: str, body: str) -> GuardOutcome:
        return await self._outbound(
            "sms",
            "sms",
            self.config.max_sms_per_day,
            call_sid,
            to,
            lambda: self.inner.send_sms(call_sid, to, body),
        )

    def status(self) -> dict[str, object]:
        """Limits and today's counters for /health (never the numbers themselves)."""
        try:
            counts: dict[str, int] | str = self.counters.counts()
        except CounterStoreError:
            counts = "unavailable"
        return {
            "dry_run": self.config.dry_run,
            "allowlist_size": len(self.config.allowlist),
            "max_outbound_calls_per_day": self.config.max_calls_per_day,
            "max_sms_per_day": self.config.max_sms_per_day,
            "today": counts,
        }

    # ------------------------------------------------------------------ internals
    async def _outbound(self, kind, counter: CounterKind, cap, call_sid, to, start):
        if not is_e164(to):
            return self._log(GuardOutcome.REFUSED_INVALID_NUMBER, kind, call_sid)
        if self.config.own_number and to == self.config.own_number:
            return self._log(GuardOutcome.REFUSED_OWN_NUMBER, kind, call_sid, to)
        if to not in self.config.allowlist:
            return self._log(GuardOutcome.REFUSED_NOT_ALLOWLISTED, kind, call_sid, to)
        if self._seen(call_sid, kind):
            return self._log(GuardOutcome.DUPLICATE, kind, call_sid, to)
        self._mark(call_sid, kind)
        if self.config.dry_run:
            return self._log(GuardOutcome.DRY_RUN, kind, call_sid, to)
        try:
            reserved = self.counters.try_reserve(counter, cap)
        except CounterStoreError as exc:
            log_event(logger, logging.ERROR, "telephony_counter_error", error=str(exc))
            return self._log(GuardOutcome.REFUSED_COUNTER_ERROR, kind, call_sid, to)
        if not reserved:
            return self._log(GuardOutcome.REFUSED_DAILY_CAP, kind, call_sid, to, cap=cap)
        return await self._run(kind, call_sid, start(), to)

    async def _run(self, kind: str, call_sid: str, coro, to: str | None = None) -> GuardOutcome:
        try:
            await coro
        except Exception as exc:  # noqa: BLE001 - report, never crash the call
            log_event(
                logger,
                logging.ERROR,
                "telephony_action_failed",
                action=kind,
                call_id=call_sid,
                error_type=type(exc).__name__,
            )
            return GuardOutcome.FAILED
        return self._log(GuardOutcome.EXECUTED, kind, call_sid, to)

    def _seen(self, call_sid: str, kind: str) -> bool:
        return kind in self._done.get(call_sid, ())

    def _mark(self, call_sid: str, kind: str) -> None:
        self._done.setdefault(call_sid, set()).add(kind)
        self._done.move_to_end(call_sid)
        while len(self._done) > self.config.dedupe_memory:
            self._done.popitem(last=False)

    def _log(
        self, outcome: GuardOutcome, kind: str, call_sid: str, to: str | None = None, **extra
    ) -> GuardOutcome:
        level = logging.INFO
        if outcome.value.startswith("refused"):
            level = logging.WARNING
        event = "telephony_would_" + kind if outcome is GuardOutcome.DRY_RUN else "telephony_guard"
        log_event(
            logger,
            level,
            event,
            action=kind,
            outcome=outcome.value,
            call_id=call_sid,
            to=mask_number(to) if to else None,
            **extra,
        )
        return outcome
