"""Rolling, speaker-labelled transcript window kept only in RAM for one call."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

Speaker = Literal["caller", "senior"]


@dataclass(frozen=True)
class Utterance:
    at: float
    speaker: Speaker
    text: str


class TranscriptWindow:
    """Keeps the last `max_age_seconds` of recognised speech. Never persisted or logged."""

    def __init__(
        self,
        max_age_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        max_utterances: int = 200,
    ) -> None:
        self.max_age_seconds = max_age_seconds
        self._clock = clock
        self._items: deque[Utterance] = deque(maxlen=max_utterances)

    def add(self, speaker: Speaker, text: str) -> None:
        text = " ".join(text.split())
        if text:
            self._items.append(Utterance(self._clock(), speaker, text))
        self._prune()

    def _prune(self) -> None:
        cutoff = self._clock() - self.max_age_seconds
        while self._items and self._items[0].at < cutoff:
            self._items.popleft()

    def text(self) -> str:
        """Plain text of the window (input for the keyword rules)."""
        self._prune()
        return " ".join(u.text for u in self._items)

    def render(self) -> str:
        """Speaker-labelled lines (state for the decision model)."""
        self._prune()
        return "\n".join(f"{u.speaker}: {u.text}" for u in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def clear(self) -> None:
        self._items.clear()
