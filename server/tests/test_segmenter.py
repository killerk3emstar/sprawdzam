import numpy as np
import pytest

from app.audio.segmenter import PauseSegmenter

RATE = 16000


def tone(seconds: float, amplitude: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (amplitude * np.sin(2 * np.pi * 300 * t)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * RATE), dtype=np.float32)


def feed(segmenter: PauseSegmenter, *parts: np.ndarray, chunk: int = 320) -> list[np.ndarray]:
    """Feed in 20 ms chunks like the call pipeline; returns the emitted segments."""
    audio = np.concatenate(parts)
    out = []
    for i in range(0, audio.size, chunk):
        out += segmenter.push(audio[i : i + chunk])
    return out


def seconds(segment: np.ndarray) -> float:
    return segment.size / RATE


def test_cuts_at_pause_after_min_length():
    segments = feed(PauseSegmenter(), tone(3.5), silence(0.6), tone(4.0), silence(0.6))
    assert len(segments) == 2
    assert 3.5 <= seconds(segments[0]) <= 3.5 + 0.2 + 0.2 + 0.05  # pre-roll and tail kept short
    assert 4.0 <= seconds(segments[1]) <= 4.0 + 0.45


def test_short_pause_inside_min_length_does_not_cut():
    # 1.5 s + 0.5 s pause + 2 s: the first part is shorter than 3 s, so it stays one segment.
    segments = feed(PauseSegmenter(), tone(1.5), silence(0.5), tone(2.0), silence(0.6))
    assert len(segments) == 1
    assert seconds(segments[0]) >= 4.0


def test_long_monologue_is_cut_at_max_length():
    segments = feed(PauseSegmenter(max_seconds=8.0), tone(17.0))
    assert [round(seconds(s), 2) for s in segments] == [8.0, 8.0]


def test_short_utterance_emitted_after_long_pause():
    segments = feed(PauseSegmenter(), tone(1.2), silence(1.2))
    assert len(segments) == 1 and 1.2 <= seconds(segments[0]) <= 1.7


def test_noise_blip_is_dropped_and_silence_never_emitted():
    segmenter = PauseSegmenter()
    assert feed(segmenter, silence(5.0)) == []
    assert feed(segmenter, tone(0.2), silence(2.0)) == []


def test_quiet_audio_below_threshold_is_silence():
    assert feed(PauseSegmenter(speech_rms=0.01), tone(5.0, amplitude=0.005), silence(1.0)) == []


def test_reset_and_validation():
    segmenter = PauseSegmenter()
    feed(segmenter, tone(2.0))
    segmenter.reset()
    assert feed(segmenter, silence(1.5)) == []
    with pytest.raises(ValueError):
        PauseSegmenter(min_seconds=8, max_seconds=3)
