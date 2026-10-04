"""Per-call audio pipeline: audio -> speech segments -> STT -> transcript -> risk engine.

Two inputs: the caller (mu-law 8 kHz from the provider stream, `feed_mulaw`) and the senior
(PCM16 16 kHz from the app's microphone, `feed_senior_pcm16`). Each has its own pause
segmenter; both share one sequential STT worker (Whisper is a single shared server), which
always takes caller segments first. A senior segment also waits (up to SENIOR_HOLD_SECONDS)
while the caller is mid-utterance, so the caller's text is in the transcript before the
echo guard judges the senior's (`app.echo_guard`). Risk is evaluated after every caller
utterance, and after a senior utterance when no caller segment is waiting.

All state (audio buffers, transcript) lives in this object only, in RAM, and is dropped in
`close()`. The WebSocket receive loops only do cheap work; speech-to-text and risk scoring
run in the background worker so slow models never stall the media streams.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from typing import TYPE_CHECKING

import numpy as np

from app.audio.convert import pcm16le_to_float32
from app.audio.g711 import mulaw_decode, to_float32
from app.audio.resample import STT_RATE, StreamResampler
from app.audio.segmenter import PauseSegmenter
from app.config import Lang
from app.echo_guard import EchoGuard
from app.logging_setup import log_event
from app.risk.engine import CallRiskMonitor
from app.stt.base import STTBackend, STTError
from app.transcript import Speaker, TranscriptWindow

if TYPE_CHECKING:
    from app.events import EventBus

logger = logging.getLogger(__name__)

_EMPTY = np.zeros(0, dtype=np.float32)
SENIOR_HOLD_SECONDS = 8.0  # = the longest caller segment
# Senior context older than this is skipped (keeps the shared Whisper free for the caller).
SENIOR_MAX_WAIT_SECONDS = 12.0
SENIOR_STT_TIMEOUT = 3.0
_POLL_SECONDS = 0.1


class CallSession:
    def __init__(
        self,
        *,
        call_sid: str,
        stream_sid: str,
        lang: Lang,
        stt: STTBackend,
        monitor: CallRiskMonitor,
        segmenter: PauseSegmenter | None = None,
        senior_segmenter: PauseSegmenter | None = None,
        stt_timeout: float = 3.0,
        queue_size: int = 4,
        analyse: bool = True,
        analyse_senior: bool = True,
        transcript_max_age: float = 60.0,
        events: EventBus | None = None,
        echo_guard: EchoGuard | None = None,
    ) -> None:
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.lang = lang
        self.stt = stt
        self.monitor = monitor
        self.segmenter = segmenter or PauseSegmenter(STT_RATE)
        self.senior_segmenter = senior_segmenter or PauseSegmenter(
            STT_RATE, min_seconds=1.5, max_seconds=5.0, adaptive=True
        )
        # False for whitelisted contacts: audio is only resampled for the bridge, never
        # segmented, transcribed or scored.
        self.analyse = analyse
        self.analyse_senior = analyse and analyse_senior
        self.stt_timeout = stt_timeout
        self.events = events
        self.echo_guard = echo_guard or EchoGuard()
        self.transcript = TranscriptWindow(max_age_seconds=transcript_max_age)
        self.resampler = StreamResampler()
        # Pending segments per speaker (oldest dropped when full) + (enqueued at, audio).
        self._pending: dict[Speaker, deque[tuple[float, np.ndarray]]] = {
            "caller": deque(),
            "senior": deque(),
        }
        self._queue_size = queue_size
        self._wake = asyncio.Event()
        self._closing = False
        self._worker: asyncio.Task[None] | None = None
        self.stats = {
            "frames": 0,
            "segments": 0,
            "senior_segments": 0,
            "dropped_segments": 0,
            "stt_errors": 0,
            "echo_dropped": 0,
            "echo_trimmed": 0,
        }
        self.degraded = False
        self.closed = False

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self.analyse:
            self._worker = asyncio.create_task(self._run(), name=f"call-{self.call_sid}")

    async def close(self, drain_timeout: float = 2.0) -> None:
        """Stop the worker (letting queued segments finish for up to `drain_timeout` s) and
        drop all audio and transcript data, also when the caller is cancelled."""
        if self.closed:
            return
        self.closed = True
        worker = self._worker
        try:
            if worker is not None:
                self._pending["senior"].clear()  # the call is over: caller context only
                self._closing = True
                self._wake.set()
                try:
                    await asyncio.wait_for(asyncio.shield(worker), drain_timeout)
                except TimeoutError:
                    log_event(logger, logging.WARNING, "call_drain_timeout", call_id=self.call_sid)
        finally:
            if worker is not None and not worker.done():
                worker.cancel()
            self.segmenter.reset()
            self.senior_segmenter.reset()
            for pending in self._pending.values():
                pending.clear()
            self.transcript.clear()
            self.echo_guard.clear()
            log_event(
                logger,
                logging.INFO,
                "call_session_closed",
                call_id=self.call_sid,
                degraded=self.degraded,
                **self.stats,
            )

    # ------------------------------------------------------------------ input
    def feed_mulaw(self, payload: bytes) -> np.ndarray:
        """Add one media frame (mu-law 8 kHz). Returns the newly resampled 16 kHz float32
        audio (possibly empty), which the bridge forwards to the senior's app."""
        if self.closed or not payload:
            return _EMPTY
        self.stats["frames"] += 1
        pcm16k = self.resampler.process(to_float32(mulaw_decode(payload)))
        if self.analyse:
            for segment in self.segmenter.push(pcm16k):
                self._enqueue("caller", segment)
        return pcm16k

    def feed_senior_pcm16(self, data: bytes) -> None:
        """Add the senior's microphone audio (PCM16 LE 16 kHz from the app)."""
        if self.closed or not self.analyse_senior or not data or len(data) % 2:
            return
        for segment in self.senior_segmenter.push(pcm16le_to_float32(data)):
            self._enqueue("senior", segment)

    def _enqueue(self, speaker: Speaker, segment: np.ndarray) -> None:
        if logger.isEnabledFor(logging.DEBUG):
            segmenter = self.segmenter if speaker == "caller" else self.senior_segmenter
            log_event(
                logger,
                logging.DEBUG,
                "segment_cut",
                call_id=self.call_sid,
                speaker=speaker,
                **segmenter.last_cut,
            )
        pending = self._pending[speaker]
        if len(pending) >= self._queue_size:
            # Backpressure: STT is slower than real time; keep the freshest audio.
            pending.popleft()
            self.stats["dropped_segments"] += 1
            log_event(
                logger, logging.WARNING, "stt_backlog_drop", call_id=self.call_sid, speaker=speaker
            )
        pending.append((time.monotonic(), segment))
        self._wake.set()

    # ------------------------------------------------------------------ worker
    def _next(self) -> tuple[Speaker, float, np.ndarray] | None:
        """Caller first; a senior segment waits while the caller is mid-utterance (bounded)."""
        if self._pending["caller"]:
            return ("caller", *self._pending["caller"].popleft())
        senior = self._pending["senior"]
        while senior and time.monotonic() - senior[0][0] > SENIOR_MAX_WAIT_SECONDS:
            senior.popleft()
            self.stats["dropped_segments"] += 1
            log_event(logger, logging.INFO, "senior_segment_stale", call_id=self.call_sid)
        if senior:
            enqueued_at = senior[0][0]
            caller_speaking = self.segmenter.in_segment and not self._closing
            if not caller_speaking or time.monotonic() - enqueued_at >= SENIOR_HOLD_SECONDS:
                return ("senior", *senior.popleft())
        return None

    async def _run(self) -> None:
        while True:
            item = self._next()
            if item is None:
                if self._closing:
                    return
                self._wake.clear()
                if self._pending["senior"]:
                    # Held senior segment: re-check soon even without new audio.
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._wake.wait(), _POLL_SECONDS)
                else:
                    await self._wake.wait()
                continue
            speaker, enqueued_at, segment = item
            try:
                await self._process(speaker, segment, enqueued_at)
            except Exception as exc:  # noqa: BLE001 - never kill the worker
                log_event(
                    logger,
                    logging.ERROR,
                    "call_segment_failed",
                    call_id=self.call_sid,
                    speaker=speaker,
                    error_type=type(exc).__name__,
                )

    async def _process(
        self, speaker: Speaker, segment: np.ndarray, enqueued_at: float | None = None
    ) -> None:
        self.stats["segments" if speaker == "caller" else "senior_segments"] += 1
        started = time.perf_counter()
        wait_ms = None if enqueued_at is None else round((time.monotonic() - enqueued_at) * 1000)
        timeout = (
            self.stt_timeout if speaker == "caller" else min(self.stt_timeout, SENIOR_STT_TIMEOUT)
        )
        try:
            text = await asyncio.wait_for(
                self.stt.transcribe(segment, STT_RATE, self.lang), timeout
            )
        except Exception as exc:  # noqa: BLE001 - STT down: fail open, call continues
            self.stats["stt_errors"] += 1
            self.degraded = True
            log_event(
                logger,
                logging.WARNING,
                "stt_failed",
                call_id=self.call_sid,
                speaker=speaker,
                backend=getattr(self.stt, "name", "?"),
                error_type=type(exc).__name__,
                reason=str(exc) if isinstance(exc, STTError) else None,
                segment_seconds=round(segment.size / STT_RATE, 2),
            )
            return
        log_event(
            logger,
            logging.INFO,
            "stt_latency",
            call_id=self.call_sid,
            speaker=speaker,
            segment_seconds=round(segment.size / STT_RATE, 2),
            ms=round((time.perf_counter() - started) * 1000),
            queue_wait_ms=wait_ms,
            chars=len(text) if isinstance(text, str) else None,
        )
        if not isinstance(text, str) or not text.strip():
            return
        if speaker == "senior":
            kept = self.echo_guard.remove_echo(text, captured_at=enqueued_at)
            if kept is None:
                self.stats["echo_dropped"] += 1
                log_event(logger, logging.INFO, "echo_dropped", call_id=self.call_sid)
                return
            if kept != text:
                self.stats["echo_trimmed"] += 1
                log_event(
                    logger,
                    logging.INFO,
                    "echo_trimmed",
                    call_id=self.call_sid,
                    words_before=len(text.split()),
                    words_after=len(kept.split()),
                )
                text = kept
        else:
            self.echo_guard.add_caller(text, at=enqueued_at)
        self.transcript.add(speaker, text)
        if self.events is not None:
            self.events.transcript(self.call_sid, speaker, " ".join(text.split()))
        if speaker == "caller" or not self._pending["caller"]:
            await self.monitor.evaluate(self.transcript)
