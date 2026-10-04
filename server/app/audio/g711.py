"""G.711 mu-law codec implemented with numpy lookup tables.

Twilio Media Streams carry 8 kHz mono mu-law. The stdlib `audioop` module was removed in
Python 3.13, so we implement the codec ourselves (ITU-T G.711, the classic Sun reference
algorithm with bias 0x84 and clip 32635).
"""

from __future__ import annotations

import numpy as np

_BIAS = 0x84
_CLIP = 32635


def _build_decode_table() -> np.ndarray:
    codes = np.arange(256, dtype=np.int32)
    inverted = ~codes & 0xFF
    sign = inverted & 0x80
    exponent = (inverted >> 4) & 0x07
    mantissa = inverted & 0x0F
    magnitude = (((mantissa << 3) + _BIAS) << exponent) - _BIAS
    return np.where(sign != 0, -magnitude, magnitude).astype(np.int16)


def _encode_scalar_array(samples: np.ndarray) -> np.ndarray:
    """Vectorised mu-law encoder for an int32 array of PCM16 values."""
    sign = np.where(samples < 0, 0x80, 0x00)
    magnitude = np.minimum(np.abs(samples), _CLIP) + _BIAS
    # Exponent = position of the highest set bit above bit 7 (0..7).
    exponent = np.floor(np.log2(magnitude)).astype(np.int32) - 7
    exponent = np.clip(exponent, 0, 7)
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa) & 0xFF).astype(np.uint8)


_DECODE_TABLE = _build_decode_table()
# Indexed by the uint16 bit pattern of an int16 sample (65536 entries, 64 KiB).
_ENCODE_TABLE = _encode_scalar_array(
    np.arange(65536, dtype=np.int32).astype(np.uint16).view(np.int16).astype(np.int32)
)


def mulaw_decode(data: bytes | bytearray | memoryview) -> np.ndarray:
    """Decode mu-law bytes into int16 PCM samples."""
    codes = np.frombuffer(data, dtype=np.uint8)
    return _DECODE_TABLE[codes]


def mulaw_encode(pcm: np.ndarray) -> bytes:
    """Encode int16 PCM samples (or float samples in [-1, 1]) into mu-law bytes."""
    pcm16 = to_int16(pcm)
    return _ENCODE_TABLE[pcm16.view(np.uint16)].tobytes()


def to_int16(pcm: np.ndarray) -> np.ndarray:
    """Convert float32/float64 [-1, 1] or integer samples to int16 with clipping."""
    array = np.asarray(pcm)
    if array.dtype == np.int16:
        return array
    if np.issubdtype(array.dtype, np.floating):
        return np.clip(np.round(array * 32768.0), -32768, 32767).astype(np.int16)
    return np.clip(array, -32768, 32767).astype(np.int16)


def to_float32(pcm16: np.ndarray) -> np.ndarray:
    """Convert int16 samples to float32 in [-1, 1)."""
    return (np.asarray(pcm16, dtype=np.int16).astype(np.float32)) / 32768.0
