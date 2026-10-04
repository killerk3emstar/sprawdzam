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


def test_pcm16le_roundtrip_and_validation():
    from app.audio.convert import float32_to_pcm16le, pcm16le_to_float32

    samples = np.array([0.0, 0.5, -0.5, -1.0], dtype=np.float32)
    data = float32_to_pcm16le(samples)
    assert data[:4] == b"\x00\x00\x00\x40"  # little-endian 16384 for 0.5
    assert np.allclose(pcm16le_to_float32(data), samples, atol=1e-4)
    with pytest.raises(ValueError):
        pcm16le_to_float32(b"\x00\x01\x02")


def test_framer_keeps_remainder():
    from app.audio.convert import Framer

    framer = Framer(4)
    assert framer.push(b"abcdef") == [b"abcd"]
    assert framer.push(b"gh") == [b"efgh"]
    assert framer.push(b"i") == []


def test_pcm_to_mulaw_frames():
    from app.audio.convert import pcm_to_mulaw_frames

    frames = pcm_to_mulaw_frames(np.zeros(16000, dtype=np.float32), 16000)
    assert len(frames) == 50 and all(len(f) == 160 for f in frames)
    assert set(frames[0]) == {0xFF}  # silence in mu-law
    assert len(pcm_to_mulaw_frames((np.ones(8000) * 1000).astype(np.int16), 8000)) == 50


def test_tones():
    from app.calls import tones

    ring = tones.ringback_frames()
    assert len(ring) == 50 and all(len(f) == 160 for f in ring)
    warning = tones.warning_frames()
    assert warning and all(len(f) == 640 for f in warning)
