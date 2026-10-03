"""Per-call audio pipeline: mu-law 8 kHz -> PCM float32 16 kHz -> STT windows -> risk engine.

All state (audio buffer, transcript) lives in this object only, in RAM, and is dropped in
`close()`. The WebSocket receive loop only does cheap work (`feed_mulaw`); speech-to-text and
risk scoring run in a background worker so slow models never stall the media stream.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import numpy as np

from app.audio.g711 import mulaw_decode, to_float32
from app.audio.resample import STT_RATE, StreamResampler
from app.config import Lang
from app.logging_setup import log_event
from app.risk.engine import CallRiskMonitor
from app.stt.base import STTBackend
from app.transcript import TranscriptWindow

logger = logging.getLogger(__name__)

# Below this RMS (~ -50 dBFS) a window is treated as silence and not sent to STT.
# Placeholder for Silero VAD.
DEFAULT_SILENCE_RMS = 0.003
_EMPTY = np.zeros(0, dtype=np.float32)


class CallSession:
    def __init__(
        self,
        *,
        call_sid: str,
        stream_sid: str,
        lang: Lang,
        stt: STTBackend,
        monitor: CallRiskMonitor,
        window_seconds: float = 3.0,
        stt_timeout: float = 8.0,
        silence_rms: float = DEFAULT_SILENCE_RMS,
        queue_size: int = 4,
        transcript_max_age: float = 60.0,
    ) -> None:
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.lang = lang
        self.stt = stt
        self.monitor = monitor
        self.window_samples = int(window_seconds * STT_RATE)
        self.stt_timeout = stt_timeout
        self.silence_rms = silence_rms
        self.transcript = TranscriptWindow(max_age_seconds=transcript_max_age)
        self.resampler = StreamResampler()
        self._buffer: list[np.ndarray] = []
        self._buffered = 0
        self._queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue(maxsize=queue_size)
        self._worker: asyncio.Task[None] | None = None
        self.stats = {"frames": 0, "windows": 0, "dropped_windows": 0, "stt_errors": 0}
        self.degraded = False
        self.closed = False

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._worker = asyncio.create_task(self._run(), name=f"call-{self.call_sid}")

    async def close(self, drain_timeout: float = 2.0) -> None:
        """Stop the worker (letting queued windows finish for up to `drain_timeout` s) and
        drop all audio and transcript data, also when the caller is cancelled."""
        if self.closed:
            return
        self.closed = True
        worker = self._worker
        try:
            if worker is not None:
                if self._queue.full():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        self._queue.get_nowait()
                self._queue.put_nowait(None)
                try:
                    await asyncio.wait_for(asyncio.shield(worker), drain_timeout)
                except TimeoutError:
                    log_event(logger, logging.WARNING, "call_drain_timeout", call_id=self.call_sid)
        finally:
            if worker is not None and not worker.done():
                worker.cancel()
            self._buffer.clear()
            self._buffered = 0
            self.transcript.clear()
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
        if pcm16k.size:
            self._buffer.append(pcm16k)
            self._buffered += pcm16k.size
        while self._buffered >= self.window_samples:
            self._emit_window()
        return pcm16k

    def _emit_window(self) -> None:
        audio = np.concatenate(self._buffer)
        window, rest = audio[: self.window_samples], audio[self.window_samples :]
        self._buffer = [rest] if rest.size else []
        self._buffered = rest.size
        if self._queue.full():
            # Backpressure: STT is slower than real time; keep the freshest audio.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            self.stats["dropped_windows"] += 1
            log_event(logger, logging.WARNING, "stt_backlog_drop", call_id=self.call_sid)
        self._queue.put_nowait(window)

    # ------------------------------------------------------------------ worker
    async def _run(self) -> None:
        while True:
            window = await self._queue.get()
            if window is None:
                return
            try:
                await self._process(window)
            except Exception as exc:  # noqa: BLE001 - never kill the worker
                log_event(
                    logger,
                    logging.ERROR,
                    "call_window_failed",
                    call_id=self.call_sid,
                    error_type=type(exc).__name__,
                )

    async def _process(self, window: np.ndarray) -> None:
        self.stats["windows"] += 1
        rms = float(np.sqrt(np.mean(np.square(window, dtype=np.float64))))
        if rms < self.silence_rms:
            return
        try:
            text = await asyncio.wait_for(
                self.stt.transcribe(window, STT_RATE, self.lang), self.stt_timeout
            )
        except Exception as exc:  # noqa: BLE001 - STT down: fail open, call continues
            self.stats["stt_errors"] += 1
            self.degraded = True
            log_event(
                logger,
                logging.WARNING,
                "stt_failed",
                call_id=self.call_sid,
                backend=getattr(self.stt, "name", "?"),
                error_type=type(exc).__name__,
            )
            return
        if not isinstance(text, str) or not text.strip():
            return
        self.transcript.add("caller", text)
        await self.monitor.evaluate(self.transcript)
