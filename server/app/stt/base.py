"""Speech-to-text interface.

The real implementation (whisper.cpp HTTP server, language forced from the senior's settings)
comes later; the call pipeline only depends on this protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from app.config import Lang


class STTError(Exception):
    """Raised by STT backends when transcription fails (network, HTTP status, bad payload)."""


@runtime_checkable
class STTBackend(Protocol):
    name: str

    async def transcribe(self, audio: np.ndarray, sample_rate: int, lang: Lang) -> str:
        """Transcribe mono float32 audio in [-1, 1]. Returns plain text ("" for nothing)."""
        ...


class NoopSTT:
    """Placeholder used until whisper.cpp is wired in: hears nothing, so only rules on an
    empty transcript run and the call is never interrupted."""

    name = "noop"

    async def transcribe(self, audio: np.ndarray, sample_rate: int, lang: Lang) -> str:
        return ""
