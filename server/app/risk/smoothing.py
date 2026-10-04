"""Score smoothing so a single reading cannot interrupt a call.

* `smoothed` is the moving average of the last `window` readings (warning threshold).
* `sustained(threshold)` is true only when the last `confirmations` readings are all at or
  above the threshold (hang-up threshold). One spike, e.g. a misheard word or a model
  hiccup, can at most trigger a warning, never a hang-up.
"""

from __future__ import annotations

from collections import deque


class ScoreSmoother:
    def __init__(self, window: int = 2, confirmations: int = 2) -> None:
        if window < 1 or confirmations < 1:
            raise ValueError("window and confirmations must be >= 1")
        self.window = window
        self.confirmations = confirmations
        self._history: deque[float] = deque(maxlen=max(window, confirmations))

    def update(self, score: float) -> float:
        """Add a reading (clamped to 0..100) and return the smoothed score."""
        self._history.append(min(100.0, max(0.0, float(score))))
        return self.smoothed

    @property
    def smoothed(self) -> float:
        if not self._history:
            return 0.0
        recent = list(self._history)[-self.window :]
        return sum(recent) / len(recent)

    def sustained(self, threshold: float) -> bool:
        if len(self._history) < self.confirmations:
            return False
        return all(s >= threshold for s in list(self._history)[-self.confirmations :])

    def reset(self) -> None:
        self._history.clear()
