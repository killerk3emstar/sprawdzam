"""Echo guard for the senior's transcript.

The senior's phone plays the caller's voice (and our voice prompts) through its speaker, and
that sound can leak back into its microphone even with echo cancellation. Whisper would then
transcribe it a second time as "senior" speech. We drop a senior utterance when its
normalised text is highly similar to (or contained in) a reference text from the last
`window_seconds`, or when nearly all of its words appear in that window (an echo segment can
span the end of one caller utterance and the start of the next). References are the caller's
utterances and the prompts played to the senior. Text only, RAM only, never logged.
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
KEEP_SECONDS = 60.0
# A caller segment is cut up to its max length (8 s) after the echo of its first words was
# captured on the senior's side, so references slightly "after" the capture count too.
FUTURE_SLACK_SECONDS = 10.0


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

    def add_caller(self, text: str, at: float | None = None) -> None:
        """Reference text the senior's speaker played: caller utterances (`at` = when the
        caller's audio was captured) and voice prompts (now)."""
        norm = normalise(text)
        if norm:
            self._caller.append((self._clock() if at is None else at, norm))

    def is_echo(self, senior_text: str, captured_at: float | None = None) -> bool:
        """`captured_at` = when the senior's audio was cut (same clock); the window is measured
        from there, so a segment that waited for the STT worker is still judged correctly."""
        senior = normalise(senior_text)
        if not senior:
            return False
        now = self._clock()
        while self._caller and self._caller[0][0] < now - KEEP_SECONDS:
            self._caller.popleft()
        at = now if captured_at is None else captured_at
        recent = [
            (t, text)
            for t, text in self._caller
            if at - self.window_seconds <= t <= at + FUTURE_SLACK_SECONDS
        ]
        for _, caller in recent:
            if len(senior) >= MIN_CONTAINED_CHARS and senior in caller:
                return True
            if len(caller) >= MIN_CONTAINED_CHARS and caller in senior:
                return True
            if SequenceMatcher(None, senior, caller).ratio() >= self.ratio:
                return True
        words = senior.split()
        if len(words) >= MIN_OVERLAP_WORDS:
            caller_words = {w for _, text in recent for w in text.split()}
            if sum(w in caller_words for w in words) / len(words) >= WORD_OVERLAP:
                return True
        return False

    def clear(self) -> None:
        self._caller.clear()
