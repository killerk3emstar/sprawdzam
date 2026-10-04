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


# ---------------------------------------------------------------------- adaptive (senior mic)
RNG = np.random.default_rng(7)


def speech_like(seconds: float, level: float = 0.1, freq: float = 220.0) -> np.ndarray:
    """A tone with a 4 Hz syllable envelope at RMS ~`level`."""
    t = np.arange(int(seconds * RATE)) / RATE
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 4 * t)
    return (level * np.sqrt(2) * envelope * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def noise(seconds: float, rms: float) -> np.ndarray:
    return (rms * RNG.standard_normal(int(seconds * RATE))).astype(np.float32)


def utterances(count: int, seconds: float, gap: float, level: float = 0.1) -> np.ndarray:
    parts = []
    for _ in range(count):
        parts += [speech_like(seconds, level), silence(gap)]
    return np.concatenate(parts)


def senior_segmenter(adaptive: bool = True) -> PauseSegmenter:
    return PauseSegmenter(min_seconds=1.5, max_seconds=5.0, adaptive=adaptive)


def test_adaptive_cuts_pauses_above_a_noise_floor():
    # Speakerphone + AGC: the "pauses" sit at -30 dBFS, above the fixed -40 dBFS threshold.
    audio = utterances(4, 2.5, 0.5)
    audio = np.concatenate([noise(1.0, 0.03), audio + noise(audio.size / RATE, 0.03)])
    fixed = feed(senior_segmenter(adaptive=False), audio)
    assert [seconds(s) for s in fixed] == [5.0, 5.0]  # cut by length only
    adaptive = senior_segmenter()
    lengths = [seconds(s) for s in feed(adaptive, audio)]
    assert len(lengths) == 4 and all(1.5 <= length <= 4.0 for length in lengths)
    cut = adaptive.last_cut
    assert cut["reason"] == "pause" and 0.02 <= cut["noise_floor"] <= 0.04
    assert cut["threshold"] > 0.03 and cut["seconds"] == round(lengths[-1], 2)


def test_adaptive_cuts_on_relative_drop_over_residual_caller_echo():
    # The caller's voice leaks from the speaker 14 dB below the senior's own speech.
    audio = utterances(4, 2.0, 0.6)
    t = np.arange(audio.size) / RATE
    echo = 0.02 * np.sqrt(2) * (0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 3 * t)))
    audio = audio + (echo * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    assert all(seconds(s) == 5.0 for s in feed(senior_segmenter(adaptive=False), audio))
    lengths = [seconds(s) for s in feed(senior_segmenter(), audio)]
    assert len(lengths) == 4 and all(1.9 <= length <= 3.0 for length in lengths)


def test_adaptive_ignores_steady_noise_and_hears_quieter_speech_later():
    segmenter = senior_segmenter()
    # Steady noise: at most the first 2 s (before the floor is learned) can pass as speech.
    assert len(feed(segmenter, noise(10.0, 0.02))) <= 1
    segmenter.reset()
    loud_then_quiet = np.concatenate(
        [speech_like(2.0, 0.3), silence(5.0), speech_like(2.0, 0.03), silence(2.0)]
    )
    assert len(feed(segmenter, loud_then_quiet)) == 2


def test_fixed_mode_is_unchanged_for_the_caller():
    segmenter = PauseSegmenter()
    assert not segmenter.adaptive and segmenter.threshold == 0.01
    feed(segmenter, tone(3.5), silence(0.6))
    assert segmenter.last_cut["reason"] == "pause"
