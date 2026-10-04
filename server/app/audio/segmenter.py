"""Pause-based speech segmentation (energy VAD) for speech-to-text.

Whisper's latency hardly depends on chunk length (it always encodes a 30 s window) while
short chunks hurt accuracy, so we cut the caller's audio at natural pauses into 3-8 s
utterances instead of fixed windows. A frame (20 ms) counts as speech when its RMS is above
`speech_rms`. Silero VAD is the planned upgrade if phone noise makes the RMS rule unreliable.

Rules, applied per frame once a segment has started:
* at `max_seconds` the segment is cut (long monologue without pauses);
* after a pause of `pause_seconds`, a segment with at least `min_seconds` before the pause
  is emitted;
* after a long pause (`long_pause_seconds`) a shorter utterance is emitted if it holds at
  least `min_speech_seconds` of speech, otherwise it is dropped as noise.
Pure silence is never emitted. A short pre-roll keeps the start of the first word.
"""

from __future__ import annotations

from collections import deque

import numpy as np

DEFAULT_SPEECH_RMS = 0.01  # ~ -40 dBFS
FRAME_SECONDS = 0.02


class PauseSegmenter:
    def __init__(
        self,
        rate: int = 16000,
        *,
        min_seconds: float = 3.0,
        max_seconds: float = 8.0,
        pause_seconds: float = 0.2,
        speech_rms: float = DEFAULT_SPEECH_RMS,
        long_pause_seconds: float = 1.0,
        min_speech_seconds: float = 0.8,
        preroll_seconds: float = 0.2,
        keep_trailing_seconds: float = 0.2,
    ) -> None:
        if not 0 < min_seconds < max_seconds:
            raise ValueError("expected 0 < min_seconds < max_seconds")
        self.rate = rate
        self.frame = int(rate * FRAME_SECONDS)
        to_frames = lambda seconds: max(1, round(seconds / FRAME_SECONDS))  # noqa: E731
        self.min_frames = to_frames(min_seconds)
        self.max_frames = to_frames(max_seconds)
        self.pause_frames = to_frames(pause_seconds)
        self.long_pause_frames = max(self.pause_frames, to_frames(long_pause_seconds))
        self.min_speech_frames = to_frames(min_speech_seconds)
        self.keep_trailing = to_frames(keep_trailing_seconds)
        self.speech_rms = speech_rms
        self._pending = np.zeros(0, dtype=np.float32)
        self._preroll: deque[np.ndarray] = deque(maxlen=to_frames(preroll_seconds))
        self._segment: list[np.ndarray] = []
        self._speech_frames = 0
        self._silence_run = 0

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        """Add audio (float32 mono at `rate`); returns the segments completed by it."""
        if samples.size == 0:
            return []
        audio = np.concatenate([self._pending, np.asarray(samples, dtype=np.float32)])
        count = audio.size // self.frame
        self._pending = audio[count * self.frame :]
        out: list[np.ndarray] = []
        for i in range(count):
            segment = self._on_frame(audio[i * self.frame : (i + 1) * self.frame])
            if segment is not None:
                out.append(segment)
        return out

    def reset(self) -> None:
        self._pending = np.zeros(0, dtype=np.float32)
        self._preroll.clear()
        self._segment = []
        self._speech_frames = 0
        self._silence_run = 0

    def _on_frame(self, frame: np.ndarray) -> np.ndarray | None:
        speech = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64)))) >= self.speech_rms
        if not self._segment:
            if speech:
                self._segment = [*self._preroll, frame]
                self._preroll.clear()
                self._speech_frames, self._silence_run = 1, 0
            else:
                self._preroll.append(frame)
            return None

        self._segment.append(frame)
        if speech:
            self._speech_frames += 1
            self._silence_run = 0
        else:
            self._silence_run += 1
        length = len(self._segment)
        voiced_length = length - self._silence_run
        if length >= self.max_frames:
            return self._emit()
        if self._silence_run >= self.pause_frames and voiced_length >= self.min_frames:
            return self._emit()
        if self._silence_run >= self.long_pause_frames:
            if self._speech_frames >= self.min_speech_frames:
                return self._emit()
            self._drop()
        return None

    def _emit(self) -> np.ndarray:
        drop = max(0, self._silence_run - self.keep_trailing)
        frames = self._segment[: len(self._segment) - drop] if drop else self._segment
        audio = np.concatenate(frames)
        self._drop()
        return audio

    def _drop(self) -> None:
        self._segment = []
        self._speech_frames = 0
        self._silence_run = 0
