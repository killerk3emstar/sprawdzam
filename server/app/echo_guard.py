"""Echo guard for the senior's transcript.

The senior's phone plays the caller's voice (and our voice prompts) through its speaker, and
that sound can leak back into its microphone even with echo cancellation. Whisper would then
transcribe it a second time as "senior" speech. We drop a senior utterance when its
normalised text is highly similar to (or contained in) a reference text from the last
`window_seconds`, or when nearly all of its words appear in that window (an echo segment can
span the end of one caller utterance and the start of the next). References are the caller's
utterances and the prompts played to the senior. Text only, RAM only, never logged.

Long senior segments (speakerphone: the senior talks over the caller's voice from the
speaker) can mix echo with real senior speech, so `remove_echo()` also removes runs of at least
`MIN_RUN_WORDS` consecutive words that appear in the same order in the recent caller text
(the references concatenated, so a run may span two caller utterances) and keeps the rest.
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
MIN_RUN_WORDS = 3  # shorter shared runs ("nie wiem", "tak tak") are kept as senior speech
MIN_LEFT_WORDS = 2  # after stripping, fewer words than this = the whole segment was echo


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
        recent = self._recent(now if captured_at is None else captured_at)
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

    def remove_echo(self, senior_text: str, captured_at: float | None = None) -> str | None:
        """Senior text without the echoed parts: None if it is all echo, the original text if
        nothing matched, otherwise the remaining words (original spelling)."""
        if self.is_echo(senior_text, captured_at):
            return None
        tokens = senior_text.split()
        words: list[str] = []
        owner: list[int] = []  # word index -> token index
        for index, token in enumerate(tokens):
            for word in normalise(token).split():
                words.append(word)
                owner.append(index)
        reference = " ".join(text for _, text in self._recent(captured_at)).split()
        if len(words) < MIN_RUN_WORDS or len(reference) < MIN_RUN_WORDS:
            return senior_text
        matcher = SequenceMatcher(None, words, reference, autojunk=False)
        echoed = [False] * len(words)
        for block in matcher.get_matching_blocks():
            if block.size >= MIN_RUN_WORDS:
                for i in range(block.a, block.a + block.size):
                    echoed[i] = True
        if not any(echoed):
            return senior_text
        keep = sorted({owner[i] for i, gone in enumerate(echoed) if not gone})
        left = [tokens[i] for i in keep]
        if sum(not gone for gone in echoed) < MIN_LEFT_WORDS:
            return None
        return " ".join(left)

    def _recent(self, captured_at: float | None) -> list[tuple[float, str]]:
        at = self._clock() if captured_at is None else captured_at
        return [
            (t, text)
            for t, text in self._caller
            if at - self.window_seconds <= t <= at + FUTURE_SLACK_SECONDS
        ]

    def clear(self) -> None:
        self._caller.clear()
