"""Format conversions between the phone side (mu-law 8 kHz) and the app side (PCM16 16 kHz)."""

from __future__ import annotations

import numpy as np

from app.audio.g711 import mulaw_encode, to_int16
from app.audio.resample import TWILIO_RATE, resample

APP_RATE = 16000
APP_FRAME_SAMPLES = 320  # 20 ms at 16 kHz
APP_FRAME_BYTES = APP_FRAME_SAMPLES * 2
PHONE_FRAME_BYTES = 160  # 20 ms of mu-law at 8 kHz


def pcm16le_to_float32(data: bytes) -> np.ndarray:
    """PCM16 little-endian bytes -> float32 in [-1, 1). Raises ValueError on odd length."""
    if len(data) % 2:
        raise ValueError("PCM16 data must have an even number of bytes")
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def float32_to_pcm16le(samples: np.ndarray) -> bytes:
    return to_int16(samples).astype("<i2").tobytes()


def pcm_to_mulaw_frames(
    audio: np.ndarray, sample_rate: int, frame_bytes: int = PHONE_FRAME_BYTES
) -> list[bytes]:
    """PCM (int16, or float in [-1, 1]) at any rate -> mu-law 8 kHz frames (20 ms default)."""
    samples = np.asarray(audio)
    if np.issubdtype(samples.dtype, np.integer):
        samples = samples.astype(np.float32) / 32768.0
    mulaw = mulaw_encode(resample(samples, sample_rate, TWILIO_RATE))
    return [mulaw[i : i + frame_bytes] for i in range(0, len(mulaw), frame_bytes)]


class Framer:
    """Accumulates bytes and yields fixed-size frames (remainder kept for the next push)."""

    def __init__(self, frame_bytes: int) -> None:
        self.frame_bytes = frame_bytes
        self._buffer = bytearray()

    def push(self, data: bytes) -> list[bytes]:
        self._buffer += data
        count = len(self._buffer) // self.frame_bytes
        frames = [
            bytes(self._buffer[i * self.frame_bytes : (i + 1) * self.frame_bytes])
            for i in range(count)
        ]
        del self._buffer[: count * self.frame_bytes]
        return frames

    def clear(self) -> None:
        self._buffer.clear()
