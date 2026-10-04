"""Echo guard for the senior's transcript.

The senior's phone plays the caller's voice through its speaker, and that sound can leak
back into its microphone even with echo cancellation. Whisper would then transcribe the
caller's words a second time as "senior" speech. We drop a senior utterance when its
normalised text is highly similar to (or contained in) a caller utterance from the last
`window_seconds`, or when nearly all of its words were said by the caller in that window
(an echo segment can span the end of one caller utterance and the start of the next).
Text only, kept in RAM for the window, never logged.
"""

from __future__ import annotations

import re
import time
from collections import deque
from collections.abc import Callable
from difflib import SequenceMatcher

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
MIN_CONTAINED_CHARS = 12  # "tak" inside a caller sentence is not an echo
MIN_OVERLAP_WORDS = 4
WORD_OVERLAP = 0.85


def normalise(text: str) -> str:
    return " ".join(_NON_WORD.sub(" ", text.lower()).split())


class EchoGuard:
    def __init__(
        self,
        window_seconds: float = 15.0,
        ratio: float = 0.75,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.window_seconds = window_seconds
        self.ratio = ratio
        self._clock = clock
        self._caller: deque[tuple[float, str]] = deque(maxlen=50)

    def add_caller(self, text: str) -> None:
        norm = normalise(text)
        if norm:
            self._caller.append((self._clock(), norm))

    def is_echo(self, senior_text: str) -> bool:
        senior = normalise(senior_text)
        if not senior:
            return False
        cutoff = self._clock() - self.window_seconds
        while self._caller and self._caller[0][0] < cutoff:
            self._caller.popleft()
        for _, caller in self._caller:
            if len(senior) >= MIN_CONTAINED_CHARS and senior in caller:
                return True
            if len(caller) >= MIN_CONTAINED_CHARS and caller in senior:
                return True
            if SequenceMatcher(None, senior, caller).ratio() >= self.ratio:
                return True
        words = senior.split()
        if len(words) >= MIN_OVERLAP_WORDS:
            caller_words = {w for _, text in self._caller for w in text.split()}
            if sum(w in caller_words for w in words) / len(words) >= WORD_OVERLAP:
                return True
        return False

    def clear(self) -> None:
        self._caller.clear()
