"""Per-call audio pipeline: mu-law 8 kHz -> PCM 16 kHz -> speech segments -> STT -> risk engine.

All state (audio buffer, transcript) lives in this object only, in RAM, and is dropped in
`close()`. The WebSocket receive loop only does cheap work (`feed_mulaw`); speech-to-text and
risk scoring run in a background worker so slow models never stall the media stream.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

import numpy as np

from app.audio.g711 import mulaw_decode, to_float32
from app.audio.resample import STT_RATE, StreamResampler
from app.audio.segmenter import PauseSegmenter
from app.config import Lang
from app.logging_setup import log_event
from app.risk.engine import CallRiskMonitor
from app.stt.base import STTBackend, STTError
from app.transcript import TranscriptWindow

logger = logging.getLogger(__name__)

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
        segmenter: PauseSegmenter | None = None,
        stt_timeout: float = 3.0,
        queue_size: int = 4,
        analyse: bool = True,
        transcript_max_age: float = 60.0,
    ) -> None:
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.lang = lang
        self.stt = stt
        self.monitor = monitor
        self.segmenter = segmenter or PauseSegmenter(STT_RATE)
        # False for whitelisted contacts: audio is only resampled for the bridge, never
        # segmented, transcribed or scored.
        self.analyse = analyse
        self.stt_timeout = stt_timeout
        self.transcript = TranscriptWindow(max_age_seconds=transcript_max_age)
        self.resampler = StreamResampler()
        self._queue: asyncio.Queue[np.ndarray | None] = asyncio.Queue(maxsize=queue_size)
        self._worker: asyncio.Task[None] | None = None
        self.stats = {"frames": 0, "segments": 0, "dropped_segments": 0, "stt_errors": 0}
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
            self.segmenter.reset()
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
        if self.analyse:
            for segment in self.segmenter.push(pcm16k):
                self._enqueue(segment)
        return pcm16k

    def _enqueue(self, segment: np.ndarray) -> None:
        if self._queue.full():
            # Backpressure: STT is slower than real time; keep the freshest audio.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            self.stats["dropped_segments"] += 1
            log_event(logger, logging.WARNING, "stt_backlog_drop", call_id=self.call_sid)
        self._queue.put_nowait(segment)

    # ------------------------------------------------------------------ worker
    async def _run(self) -> None:
        while True:
            segment = await self._queue.get()
            if segment is None:
                return
            try:
                await self._process(segment)
            except Exception as exc:  # noqa: BLE001 - never kill the worker
                log_event(
                    logger,
                    logging.ERROR,
                    "call_segment_failed",
                    call_id=self.call_sid,
                    error_type=type(exc).__name__,
                )

    async def _process(self, segment: np.ndarray) -> None:
        self.stats["segments"] += 1
        started = time.perf_counter()
        try:
            text = await asyncio.wait_for(
                self.stt.transcribe(segment, STT_RATE, self.lang), self.stt_timeout
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
                reason=str(exc) if isinstance(exc, STTError) else None,
                segment_seconds=round(segment.size / STT_RATE, 2),
            )
            return
        log_event(
            logger,
            logging.INFO,
            "stt_latency",
            call_id=self.call_sid,
            segment_seconds=round(segment.size / STT_RATE, 2),
            ms=round((time.perf_counter() - started) * 1000),
            chars=len(text) if isinstance(text, str) else None,
        )
        if not isinstance(text, str) or not text.strip():
            return
        self.transcript.add("caller", text)
        await self.monitor.evaluate(self.transcript)
