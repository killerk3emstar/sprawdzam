import numpy as np
import pytest

from app.audio.g711 import mulaw_decode, mulaw_encode, to_int16
from app.audio.resample import StreamResampler, resample


def test_mulaw_known_values():
    pcm = np.array([0, 32767, -32768, 32124, -32124], dtype=np.int16)
    assert mulaw_encode(pcm) == bytes([0xFF, 0x80, 0x00, 0x80, 0x00])
    assert mulaw_decode(bytes([0x00, 0x80, 0xFF])).tolist() == [-32124, 32124, 0]


def test_mulaw_every_code_roundtrips():
    codes = bytes(range(256))
    reencoded = mulaw_encode(mulaw_decode(codes))
    # 0x7F is "negative zero" and legitimately re-encodes as 0xFF (positive zero).
    mismatches = [c for c in range(256) if reencoded[c] != c]
    assert mismatches == [0x7F]


def test_mulaw_pcm_roundtrip_error_is_bounded():
    rng = np.random.default_rng(1)
    pcm = rng.integers(-32768, 32767, size=20_000, dtype=np.int16)
    decoded = mulaw_decode(mulaw_encode(pcm)).astype(np.int32)
    error = np.abs(decoded - pcm.astype(np.int32))
    # mu-law keeps ~4 mantissa bits: error below ~1/16 of the magnitude (+ small floor).
    clipped = np.minimum(np.abs(pcm.astype(np.int32)), 32635)
    assert np.all(error <= clipped / 16 + 8 + (np.abs(pcm) > 32635) * 700)


def test_mulaw_accepts_float_input():
    floats = np.array([0.0, 0.5, -0.5, 1.5, -1.5], dtype=np.float32)
    assert mulaw_encode(floats) == mulaw_encode(to_int16(floats))
    assert len(mulaw_encode(floats)) == 5


def test_mulaw_decode_empty():
    assert mulaw_decode(b"").size == 0


@pytest.mark.parametrize(
    ("n", "src", "dst", "expected"),
    [
        (8000, 8000, 16000, 16000),
        (1234, 8000, 16000, 2468),
        (16000, 16000, 8000, 8000),
        (24000, 24000, 8000, 8000),
    ],
)
def test_one_shot_resample_length(n, src, dst, expected):
    assert len(resample(np.zeros(n, dtype=np.float32), src, dst)) == expected


def test_stream_resampler_doubles_length_and_keeps_frequency():
    resampler = StreamResampler(8000, 16000)
    t = np.arange(8000) / 8000.0
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    out = [resampler.process(tone[i : i + 160]) for i in range(0, 8000, 160)]
    out.append(resampler.flush())
    audio = np.concatenate(out)
    assert audio.size == 16000
    spectrum = np.abs(np.fft.rfft(audio))
    peak_hz = np.argmax(spectrum) * 16000 / audio.size
    assert abs(peak_hz - 1000) < 5
