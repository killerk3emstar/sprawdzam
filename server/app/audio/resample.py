"""Sample-rate conversion (libsoxr via the `soxr` package).

Incoming call audio is 8 kHz; Whisper expects 16 kHz. The streaming resampler keeps filter
state between 20 ms Twilio frames, so there are no clicks at frame boundaries. Its output is
bursty at the start (filter latency) but the total length converges to exactly 2x after
`flush()`.
"""

from __future__ import annotations

import numpy as np
import soxr

TWILIO_RATE = 8000
STT_RATE = 16000


class StreamResampler:
    """Stateful float32 mono resampler for a single call."""

    def __init__(self, in_rate: int = TWILIO_RATE, out_rate: int = STT_RATE) -> None:
        self.in_rate = in_rate
        self.out_rate = out_rate
        self._stream = soxr.ResampleStream(in_rate, out_rate, 1, dtype="float32")

    def process(self, samples: np.ndarray) -> np.ndarray:
        chunk = np.ascontiguousarray(samples, dtype=np.float32)
        return self._stream.resample_chunk(chunk)

    def flush(self) -> np.ndarray:
        return self._stream.resample_chunk(np.zeros(0, dtype=np.float32), last=True)


def resample(samples: np.ndarray, in_rate: int, out_rate: int) -> np.ndarray:
    """One-shot float32 mono resampling (e.g. a pre-rendered voice warning to 8 kHz)."""
    if in_rate == out_rate:
        return np.asarray(samples, dtype=np.float32)
    chunk = np.ascontiguousarray(samples, dtype=np.float32)
    return soxr.resample(chunk, in_rate, out_rate)
