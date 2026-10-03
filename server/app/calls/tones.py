"""Generated call tones (no audio assets needed)."""

from __future__ import annotations

from functools import cache

import numpy as np

from app.audio.convert import APP_FRAME_BYTES, APP_RATE, Framer, float32_to_pcm16le
from app.audio.g711 import mulaw_encode
from app.audio.resample import TWILIO_RATE

# Polish/European ringback: 425 Hz, 1 s on, 4 s off.
RINGBACK_HZ = 425.0
RINGBACK_ON_SECONDS = 1.0
RINGBACK_PERIOD_SECONDS = 5.0


def _tone(freq: float, seconds: float, rate: int, amplitude: float) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    tone = amplitude * np.sin(2 * np.pi * freq * t)
    fade = min(len(tone) // 2, int(0.01 * rate))  # 10 ms fade in/out, no clicks
    if fade:
        ramp = np.linspace(0.0, 1.0, fade)
        tone[:fade] *= ramp
        tone[-fade:] *= ramp[::-1]
    return tone.astype(np.float32)


@cache
def ringback_frames() -> tuple[bytes, ...]:
    """One ringback burst (1 s) as 20 ms mu-law 8 kHz frames."""
    mulaw = mulaw_encode(_tone(RINGBACK_HZ, RINGBACK_ON_SECONDS, TWILIO_RATE, 0.25))
    return tuple(mulaw[i : i + 160] for i in range(0, len(mulaw), 160))


@cache
def warning_frames() -> tuple[bytes, ...]:
    """Two short 880 Hz beeps as 20 ms PCM16 16 kHz frames for the senior's app."""
    beep = _tone(880.0, 0.15, APP_RATE, 0.3)
    gap = np.zeros(int(0.1 * APP_RATE), dtype=np.float32)
    audio = np.concatenate([beep, gap, beep, gap])
    return tuple(Framer(APP_FRAME_BYTES).push(float32_to_pcm16le(audio)))


@cache
def caller_beep_frames() -> tuple[bytes, ...]:
    """The warning beeps as 20 ms mu-law 8 kHz frames (fallback prompt for the caller)."""
    beep = _tone(880.0, 0.15, TWILIO_RATE, 0.3)
    gap = np.zeros(int(0.1 * TWILIO_RATE), dtype=np.float32)
    mulaw = mulaw_encode(np.concatenate([beep, gap, beep, gap]))
    return tuple(mulaw[i : i + 160] for i in range(0, len(mulaw), 160))
