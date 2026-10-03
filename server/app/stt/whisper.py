"""whisper.cpp `whisper-server` client (`POST /inference`).

Sends one speech segment as a 16 kHz mono PCM16 WAV with the call language forced, asks for
`verbose_json`, and keeps only segments that look like real speech: segments with a high
`no_speech_prob` and Whisper's well-known silence hallucinations ("KONIEC", "Napisy wykonane
przez...", "Thank you for watching") are dropped. Errors raise `STTError`; the call pipeline
logs them and carries on (fail-open).
"""

from __future__ import annotations

import io
import re
import time
import unicodedata
import wave
from typing import Any

import httpx
import numpy as np

from app.audio.convert import float32_to_pcm16le
from app.config import Lang
from app.stt.base import STTError

NO_SPEECH_MAX = 0.6
MAX_TEXT_CHARS = 2000

# Normalised (lowercase, no diacritics/punctuation) texts Whisper invents on silence/noise.
_HALLUCINATIONS = re.compile(
    r"^(?:"
    r"koniec|dziekuje|dziekuje za uwage|dzieki za uwage|dziekuje za obejrzenie"
    r"|dzieki za obejrzenie|do zobaczenia|napisy (?:wykonane|stworzone|przygotowane|by)\b.*"
    r"|tlumaczenie\b.*|subskrybuj\b.*|zapraszam (?:do subskrypcji|na kanal)\b.*"
    r"|thank you|thanks for watching|thank you for watching|thank you very much"
    r"|please subscribe\b.*|subtitles by\b.*|the end|bye|you"
    r"|.*\bamara org\b.*"
    r")$"
)


def _normalise(text: str) -> str:
    text = text.translate(str.maketrans({"ł": "l", "Ł": "L"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def is_hallucination(text: str) -> bool:
    normalised = _normalise(text)
    return not normalised or bool(_HALLUCINATIONS.fullmatch(normalised))


def to_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(float32_to_pcm16le(audio))
    return buffer.getvalue()


def extract_text(payload: Any, no_speech_max: float = NO_SPEECH_MAX) -> str:
    """Text of a `verbose_json` (or plain `json`) response, filtered. Raises STTError."""
    if not isinstance(payload, dict):
        raise STTError("unexpected response shape")
    segments = payload.get("segments")
    if segments is None:
        text = payload.get("text")
        if not isinstance(text, str):
            raise STTError("response has neither segments nor text")
        parts = [text]
    else:
        if not isinstance(segments, list):
            raise STTError("segments is not a list")
        parts = []
        for segment in segments:
            if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
                raise STTError("malformed segment")
            no_speech = segment.get("no_speech_prob", 0.0)
            if isinstance(no_speech, int | float) and no_speech > no_speech_max:
                continue
            parts.append(segment["text"])
    kept = [p.strip() for p in parts if p.strip() and not is_hallucination(p)]
    return " ".join(" ".join(kept).split())[:MAX_TEXT_CHARS]


class WhisperSTT:
    name = "whisper"

    def __init__(
        self,
        url: str,
        timeout: float = 3.0,
        client: httpx.AsyncClient | None = None,
        no_speech_max: float = NO_SPEECH_MAX,
    ) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.no_speech_max = no_speech_max
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self.last_latency_ms: float | None = None

    async def transcribe(self, audio: np.ndarray, sample_rate: int, lang: Lang) -> str:
        files = {"file": ("segment.wav", to_wav(audio, sample_rate), "audio/wav")}
        data = {
            "language": lang,
            "response_format": "verbose_json",
            "temperature": "0.0",
            "temperature_inc": "0.2",
        }
        started = time.perf_counter()
        try:
            response = await self._client.post(
                f"{self.url}/inference", files=files, data=data, timeout=self.timeout
            )
        except httpx.TimeoutException as exc:
            raise STTError("timeout") from exc
        except httpx.HTTPError as exc:
            raise STTError(f"transport error: {type(exc).__name__}") from exc
        self.last_latency_ms = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            raise STTError(f"HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise STTError("invalid JSON") from exc
        return extract_text(payload, self.no_speech_max)

    async def warm_up(self) -> float:
        """One short request so the first real segment is not slowed down. Returns ms."""
        started = time.perf_counter()
        await self.transcribe(np.zeros(16000, dtype=np.float32), 16000, "pl")
        return (time.perf_counter() - started) * 1000

    async def aclose(self) -> None:
        await self._client.aclose()
