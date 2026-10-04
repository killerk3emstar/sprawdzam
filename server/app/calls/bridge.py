"""CallBridge: one protected call between the provider media stream and the senior's app.

Lifecycle: RINGING (caller hears ringback, app notified) -> ACTIVE (after the app's
`accept`: audio bridged both ways) -> ENDED. `end()` is idempotent; it notifies the app,
closes its channel and sets `ended`, which makes the media-stream handler close the provider
socket (and so the provider ends the call).

Audio formats: phone side mu-law 8 kHz (20 ms = 160 bytes), app side PCM16 LE 16 kHz
(20 ms = 640 bytes). Nothing is recorded; buffers live only in this object.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import math
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import numpy as np

from app.audio.convert import (
    APP_FRAME_BYTES,
    APP_RATE,
    PHONE_FRAME_BYTES,
    Framer,
    float32_to_pcm16le,
    pcm16le_to_float32,
)
from app.audio.g711 import mulaw_encode
from app.audio.resample import TWILIO_RATE, StreamResampler
from app.calls import tones
from app.calls.sender import SafeSender
from app.calls.voice_prompts import PromptLibrary
from app.config import Lang
from app.logging_setup import log_event
from app.prompts import VOICE_PROMPTS
from app.relay import protocol
from app.relay.protocol import EndReason
from app.relay.trusted_alert import compose_alert_text
from app.telephony.provider import TelephonyProvider

if TYPE_CHECKING:
    from app.events import EventBus
    from app.relay.hub import AppHub
    from app.risk.engine import RiskAssessment

logger = logging.getLogger(__name__)

APP_QUEUE_FRAMES = 50  # 1 s of audio towards the app; oldest dropped beyond that
# The caller always gets at least this long (or the whole timeout, if shorter) to type the
# family password after the spoken request has finished.
PASSWORD_GRACE_SECONDS = 3.0


class CallState(StrEnum):
    RINGING = "ringing"
    ACTIVE = "active"
    ENDED = "ended"


class CallBridge:
    def __init__(
        self,
        *,
        call_id: str,
        stream_id: str,
        lang: Lang,
        caller_display: str,
        provider: TelephonyProvider,
        trusted: bool = False,
        provider_out: SafeSender,
        hub: AppHub,
        accept_timeout: float = 30.0,
        password_timeout: float = 12.0,
        auto_block_seconds: float = 8.0,
        family_password: str = "",
        prompts: PromptLibrary | None = None,
        events: EventBus | None = None,
    ) -> None:
        self.call_id = call_id
        self.stream_id = stream_id
        self.lang = lang
        self.caller_display = caller_display
        self.trusted = trusted
        self.provider = provider
        self.provider_out = provider_out
        self.hub = hub
        self.accept_timeout = accept_timeout
        self.password_timeout = password_timeout
        self.auto_block_seconds = auto_block_seconds
        self._family_password = family_password
        self.prompts = prompts
        self.events = events
        self.last_assessment: RiskAssessment | None = None
        # Senior's microphone audio for speech-to-text (set by the stream handler).
        self.senior_audio_sink: Callable[[bytes], None] | None = None
        # Text of every voice prompt played to the senior (echo guard reference).
        self.played_text_sink: Callable[[str], None] | None = None
        # Follow-up (REST hang-up, trusted-person call) when the senior hangs up on a
        # high-risk call outside the password / confirm stage (set by the stream handler).
        self.on_senior_blocked: Callable[[], Awaitable[None]] | None = None

        self.state = CallState.RINGING
        self.ended = asyncio.Event()
        self.end_reason: EndReason | None = None
        self.app: SafeSender | None = None
        self.verified = False

        self._to_app: asyncio.Queue[bytes] = asyncio.Queue(maxsize=APP_QUEUE_FRAMES)
        self._app_framer = Framer(APP_FRAME_BYTES)
        self._phone_framer = Framer(PHONE_FRAME_BYTES)
        self._phone_resampler = StreamResampler(APP_RATE, TWILIO_RATE)
        self._tasks: set[asyncio.Task[Any]] = set()  # cancelled by end()
        self._background: set[asyncio.Task[Any]] = set()  # awaited after the call
        self._ringback: asyncio.Task[Any] | None = None
        self._accept_timer: asyncio.Task[Any] | None = None
        self._dtmf = ""
        self._verify_future: asyncio.Future[bool] | None = None
        # "verify" (verify_password pending) or "confirm" (confirm_block countdown) or None.
        self.stage: str | None = None
        self.stats = {"to_app_frames": 0, "to_phone_frames": 0, "dropped_to_app": 0}
        # While a prompt plays to one side, that side's live audio from the other is muted.
        self._app_prompt = asyncio.Lock()
        self._caller_prompt = asyncio.Lock()

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if self.events is not None:
            self.events.call_started(
                self.call_id, self.caller_display, self.lang, analysed=not self.trusted
            )
        token = self.hub.register(self)
        delivered = await self.hub.broadcast(
            protocol.incoming_call(
                self.call_id, token, self.caller_display, self.lang, trusted=self.trusted
            )
        )
        log_event(
            logger,
            logging.INFO,
            "app_notified_incoming_call",
            call_id=self.call_id,
            delivered=delivered,
        )
        self._ringback = self._spawn(self._ringback_loop())
        self._accept_timer = self._spawn(self._accept_timeout())

    def attach_app(self, sender: SafeSender) -> bool:
        if self.app is not None or self.state is CallState.ENDED:
            return False
        self.app = sender
        self._spawn(self._app_sender())
        log_event(logger, logging.INFO, "app_call_channel_attached", call_id=self.call_id)
        return True

    async def accept(self) -> None:
        if self.state is not CallState.RINGING or self.app is None:
            return
        self.state = CallState.ACTIVE
        for task in (self._ringback, self._accept_timer):
            if task is not None:
                task.cancel()
        # Drop ringback audio the provider may still have buffered.
        await self.provider_out.send_json(self.provider.clear_message(self.stream_id))
        log_event(logger, logging.INFO, "call_accepted", call_id=self.call_id)

    async def end(self, reason: EndReason) -> None:
        if self.state is CallState.ENDED:
            return
        self.state = CallState.ENDED
        self.end_reason = reason
        self.ended.set()
        current = asyncio.current_task()
        for task in list(self._tasks):
            if task is not current:
                task.cancel()
        if self._verify_future is not None and not self._verify_future.done():
            self._verify_future.set_result(False)
        if self.app is not None:
            await self.app.send_json(protocol.call_ended(reason))
            await self.app.close(protocol.CLOSE_NORMAL)
        self.hub.unregister(self.call_id)
        self._app_framer.clear()
        self._phone_framer.clear()
        self._dtmf = ""
        if self.events is not None:
            if reason is EndReason.SCAM_BLOCKED:
                self.events.action(self.call_id, "hangup", "call ended by the protection service")
            self.events.call_ended(self.call_id, reason.value)
        if reason is EndReason.SCAM_BLOCKED:
            await self._alert_trusted_person()
        log_event(
            logger,
            logging.INFO,
            "call_ended",
            call_id=self.call_id,
            reason=reason.value,
            verified=self.verified,
            **self.stats,
        )

    async def _alert_trusted_person(self) -> None:
        """Ask the senior's phone to text the trusted person (the hub sends it once)."""
        assessment = self.last_assessment
        scam_type = assessment.scam_type.value if assessment else "none"
        reasons = [name for name, on in assessment.categories.items() if on] if assessment else []
        text = compose_alert_text(
            scam_type,
            reasons,
            self.lang,
            at=datetime.now(UTC),
            caller=self.caller_display,
            money_ask=assessment.rules.money_ask if assessment else None,
        )
        try:
            await self.hub.send_trusted_alert(
                self.call_id,
                protocol.alert_trusted(self.call_id, scam_type, reasons, self.lang, text),
            )
        except Exception as exc:  # noqa: BLE001 - never break the call teardown
            log_event(
                logger,
                logging.ERROR,
                "trusted_alert_failed",
                call_id=self.call_id,
                error_type=type(exc).__name__,
            )

    @property
    def high_risk(self) -> bool:
        """In the password / confirm stage, or the model's own score is sustained at or
        above the hang-up threshold."""
        if self.stage is not None:
            return True
        assessment = self.last_assessment
        return bool(assessment is not None and getattr(assessment, "model_high", False))

    async def senior_hangup(self) -> EndReason:
        """The senior pressed hang up. During high risk this counts as blocking the scam
        (`scam_blocked`: trusted person alerted, console shows it as blocked); otherwise it
        is a normal `senior_hangup`."""
        if self.state is not CallState.ACTIVE or not self.high_risk:
            await self.end(EndReason.SENIOR_HANGUP)
            return EndReason.SENIOR_HANGUP
        in_stage = self.stage is not None
        if self.events is not None:
            self.events.action(self.call_id, "senior_blocked", "senior hung up during high risk")
        log_event(logger, logging.WARNING, "senior_blocked", call_id=self.call_id, stage=self.stage)
        await self.end(EndReason.SCAM_BLOCKED)
        # In a stage the responder's own block path finishes the follow-up.
        if not in_stage and self.on_senior_blocked is not None:
            self.spawn_background(self.on_senior_blocked())
        return EndReason.SCAM_BLOCKED

    async def app_detached(self) -> None:
        if self.state is not CallState.ENDED:
            log_event(logger, logging.WARNING, "app_call_channel_dropped", call_id=self.call_id)
            await self.end(EndReason.ERROR)

    def spawn_background(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """Run work that must finish even after the call ends (alerts to the trusted person)."""
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    async def wait_background(self, limit_seconds: float = 5.0) -> None:
        if self._background:
            await asyncio.wait(set(self._background), timeout=limit_seconds)

    def _spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ------------------------------------------------------------------ audio
    async def on_caller_audio(self, pcm16k: np.ndarray) -> None:
        """Caller audio (float32, 16 kHz, from the STT resampler) towards the app."""
        if self.state is not CallState.ACTIVE or self.app is None or pcm16k.size == 0:
            return
        if self._app_prompt.locked():
            return  # the senior is hearing a prompt
        for frame in self._app_framer.push(float32_to_pcm16le(pcm16k)):
            self._queue_to_app(frame)

    def _queue_to_app(self, frame: bytes) -> None:
        if self._to_app.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._to_app.get_nowait()
            self.stats["dropped_to_app"] += 1
        self._to_app.put_nowait(frame)

    async def _app_sender(self) -> None:
        while self.app is not None:
            frame = await self._to_app.get()
            if await self.app.send_bytes(frame):
                self.stats["to_app_frames"] += 1

    async def on_app_audio(self, data: bytes) -> bool:
        """Senior's microphone (PCM16 LE 16 kHz) towards the caller. False if dropped."""
        if self.state is not CallState.ACTIVE:
            return False
        if not data or len(data) > protocol.MAX_APP_AUDIO_FRAME_BYTES or len(data) % 2:
            return False
        if self.senior_audio_sink is not None:
            # Analysed even while a prompt plays to the caller (the senior may still talk).
            self.senior_audio_sink(data)
        if self._caller_prompt.locked():
            return False
        audio8k = self._phone_resampler.process(pcm16le_to_float32(data))
        for frame in self._phone_framer.push(mulaw_encode(audio8k)):
            if await self.provider_out.send_json(
                self.provider.media_message(self.stream_id, frame)
            ):
                self.stats["to_phone_frames"] += 1
        return True

    # ------------------------------------------------------------------ prompts
    def _app_prompt_frames(self, name: str) -> tuple[bytes, ...]:
        frames = self.prompts.app_frames(name, self.lang) if self.prompts else None
        return frames or tones.warning_frames()

    def _caller_prompt_frames(self, name: str) -> tuple[bytes, ...]:
        frames = self.prompts.phone_frames(name, self.lang) if self.prompts else None
        return frames or tones.caller_beep_frames()

    async def _paced(self, frames: tuple[bytes, ...], send) -> None:
        """Send 20 ms frames in real time (100 ms ahead), so live audio queued after the prompt
        does not pile up behind it."""
        loop = asyncio.get_running_loop()
        start = loop.time()
        for i, frame in enumerate(frames):
            if self.state is CallState.ENDED:
                return
            await send(frame)
            delay = start + (i + 1) * 0.02 - 0.1 - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)

    async def play_to_app(self, *names: str) -> None:
        """Play prompts to the senior; caller audio to the app is muted meanwhile."""
        if self.app is None or self.state is not CallState.ACTIVE:
            return
        async with self._app_prompt:
            while not self._to_app.empty():  # drop caller audio queued before the prompt
                self._to_app.get_nowait()
            app = self.app
            for name in names:
                text = VOICE_PROMPTS.get(name, {}).get(self.lang)
                if text and self.played_text_sink is not None:
                    self.played_text_sink(text)
                await self._paced(self._app_prompt_frames(name), app.send_bytes)

    async def play_to_caller(self, name: str) -> None:
        """Play a prompt to the caller; the senior's audio to the caller is muted meanwhile."""
        if self.state is CallState.ENDED:
            return
        if self._ringback is not None:
            self._ringback.cancel()
        async with self._caller_prompt:
            await self.provider_out.send_json(self.provider.clear_message(self.stream_id))

            async def send(frame: bytes) -> None:
                await self.provider_out.send_json(
                    self.provider.media_message(self.stream_id, frame)
                )

            await self._paced(self._caller_prompt_frames(name), send)

    async def play_warning(self) -> None:
        """Spoken warning (or beeps) for the senior, in the background."""
        if self.events is not None:
            self.events.action(self.call_id, "warn", "spoken warning to the senior")
        if self.app is not None and self.state is CallState.ACTIVE:
            self._spawn(self.play_to_app("warning"))

    async def play_blocked_notice(self) -> None:
        """Tell the caller the call is being ended (played before `end`)."""
        await self.play_to_caller("blocked")

    async def _ringback_loop(self) -> None:
        while True:
            for frame in tones.ringback_frames():
                await self.provider_out.send_json(
                    self.provider.media_message(self.stream_id, frame)
                )
            await asyncio.sleep(tones.RINGBACK_PERIOD_SECONDS)

    async def _accept_timeout(self) -> None:
        await asyncio.sleep(self.accept_timeout)
        if self.state is CallState.RINGING:
            log_event(
                logger,
                logging.INFO,
                "call_not_accepted",
                call_id=self.call_id,
                timeout=self.accept_timeout,
            )
            await self.end(EndReason.TIMEOUT)

    # ------------------------------------------------------------------ events
    async def send_event(self, message: dict[str, object]) -> None:
        if self.app is not None and self.state is not CallState.ENDED:
            await self.app.send_json(message)

    async def send_risk(self, assessment: RiskAssessment) -> None:
        self.last_assessment = assessment
        message = protocol.risk_event(assessment)
        if self.events is not None:
            self.events.risk(
                self.call_id,
                score=message["score"],  # type: ignore[arg-type]
                model_score=None if assessment.model is None else round(assessment.model.risk),
                rules_score=assessment.rules.score,
                level=message["level"],  # type: ignore[arg-type]
                scam_type=assessment.scam_type.value,
                reasons=message["reasons"],  # type: ignore[arg-type]
                source=assessment.source,
            )
        await self.send_event(message)

    def on_dtmf(self, digits: str) -> None:
        """Keypad digits from the caller (provider) or the senior (app). RAM only, not logged."""
        self._dtmf = (self._dtmf + digits)[-32:]
        future = self._verify_future
        password = self._family_password
        if future is None or future.done() or not password or len(self._dtmf) < len(password):
            return
        if hmac.compare_digest(self._dtmf[-len(password) :].encode(), password.encode()):
            future.set_result(True)

    def password_timeout_for(self) -> int:
        """Seconds from `verify_password` to the block: PASSWORD_TIMEOUT_SECONDS, stretched so
        the caller has a moment to type after the spoken request ends."""
        prompt = len(self._caller_prompt_frames("password")) * 0.02
        grace = min(PASSWORD_GRACE_SECONDS, self.password_timeout)
        return max(1, math.ceil(max(self.password_timeout, prompt + grace)))

    async def verify_family_password(self, warn_first: bool = False) -> bool:
        """High risk. With a family password: `verify_password` to the app and a spoken request
        to both sides (the senior hears the warning first if `warn_first`); True when the
        correct digits arrive within `timeoutSeconds` of the message. Without one:
        `confirm_block` countdown, always False (blocked when it runs out or the senior hangs
        up). False on call end."""
        if self.state is CallState.ENDED:
            return False
        if not self._family_password:
            return await self._confirm_block(warn_first)
        timeout = self.password_timeout_for()
        self._dtmf = ""  # digits count from the request on
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._verify_future = future
        self.stage = "verify"
        await self.send_event(protocol.verify_password(timeout))
        if self.events is not None:
            self.events.action(self.call_id, "verify_password", "family password requested")
        app_names = ("warning", "password") if warn_first else ("password",)

        async def prompts() -> None:
            await asyncio.gather(self.play_to_caller("password"), self.play_to_app(*app_names))

        playing = self._spawn(prompts())
        try:
            await asyncio.wait_for(asyncio.shield(future), timeout)
        except TimeoutError:
            pass
        finally:
            self._verify_future = None
            self.stage = None
            if not playing.done():
                playing.cancel()
        self.verified = future.done() and future.result()
        if self.events is not None:
            self.events.action(
                self.call_id,
                "password_ok" if self.verified else "password_failed",
                "correct family password" if self.verified else "no correct password in time",
            )
        log_event(
            logger,
            logging.INFO,
            "family_password_check",
            call_id=self.call_id,
            verified=self.verified,
            timeout=timeout,
        )
        return self.verified

    async def _confirm_block(self, warn_first: bool) -> bool:
        """No family password: the app counts down `seconds`, then the call is blocked."""
        seconds = max(1, math.ceil(self.auto_block_seconds))
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._verify_future = future  # resolved (False) by end(), e.g. the senior hanging up
        self.stage = "confirm"
        await self.send_event(protocol.confirm_block(seconds))
        if self.events is not None:
            self.events.action(
                self.call_id, "confirm_block", f"no family password: blocking in {seconds} s"
            )
        if warn_first:
            self._spawn(self.play_to_app("warning"))
        try:
            await asyncio.wait_for(asyncio.shield(future), seconds)
        except TimeoutError:
            pass
        finally:
            self._verify_future = None
            self.stage = None
        log_event(logger, logging.INFO, "auto_block_countdown_done", call_id=self.call_id)
        return False
