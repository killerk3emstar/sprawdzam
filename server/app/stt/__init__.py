"""Speech-to-text backends."""

from app.stt.base import NoopSTT, STTBackend, STTError

__all__ = ["NoopSTT", "STTBackend", "STTError"]
