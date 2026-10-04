"""Opt-in tests against the real model servers (skipped by default).

    uv run pytest -m live            # needs whisper-server on :8080 and basal-serve on :8000

URLs: LIVE_WHISPER_URL / LIVE_BASAL_URL (defaults http://127.0.0.1:8080 / :8000).
Audio: LIVE_AUDIO_DIR (default ~/models/sprawdzam/audio, made by the model bench).
"""

import os
import wave
from pathlib import Path

import httpx
import numpy as np
import pytest

from app.risk.basal import BasalBackend
from app.risk.decision import DecisionRequest
from app.stt.whisper import WhisperSTT

pytestmark = [pytest.mark.live, pytest.mark.anyio]

WHISPER_URL = os.environ.get("LIVE_WHISPER_URL", "http://127.0.0.1:8080")
BASAL_URL = os.environ.get("LIVE_BASAL_URL", "http://127.0.0.1:8000")
AUDIO_DIR = Path(os.environ.get("LIVE_AUDIO_DIR", Path.home() / "models/sprawdzam/audio"))

SCAM_PL = (
    "Dzwoniący: Dzień dobry, aspirant Jan Kowalski, Komenda Miejska Policji. Pani wnuczek "
    "spowodował wypadek, potrzebna jest kaucja 30 tysięcy złotych.\n"
    "Dzwoniący: Proszę nikomu o tym nie mówić, ani córce, ani w banku. Za godzinę przyjedzie "
    "po pieniądze nasz kurier. Musimy działać natychmiast."
)
NORMAL_PL = (
    "Dzwoniący: Cześć mamo, tu Kasia. W niedzielę przyjedziemy z dziećmi na obiad, około "
    "pierwszej. Przywiozę ciasto ze śliwkami. Oddam ci te 200 zł za zakupy wieczorem."
)


def _up(url: str) -> bool:
    try:
        return httpx.get(f"{url}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="module")
def whisper_up():
    if not _up(WHISPER_URL):
        pytest.skip(f"whisper-server not reachable at {WHISPER_URL}")


@pytest.fixture(scope="module")
def basal_up():
    if not _up(BASAL_URL):
        pytest.skip(f"basal-serve not reachable at {BASAL_URL}")


async def test_whisper_transcribes_polish_phone_audio(whisper_up):
    path = AUDIO_DIR / "pl_scam_police_16k.wav"
    if not path.exists():
        pytest.skip(f"missing {path}")
    with wave.open(str(path)) as wav:
        rate = wav.getframerate()
        pcm = np.frombuffer(wav.readframes(rate * 8), dtype="<i2").astype(np.float32) / 32768
    stt = WhisperSTT(WHISPER_URL, timeout=10)
    text = (await stt.transcribe(pcm, rate, "pl")).lower()
    await stt.aclose()
    assert "aspirant" in text or "policji" in text, text


async def test_whisper_silence_gives_no_text(whisper_up):
    stt = WhisperSTT(WHISPER_URL, timeout=10)
    text = await stt.transcribe(np.zeros(16000 * 3, dtype=np.float32), 16000, "pl")
    await stt.aclose()
    assert text == ""


async def test_basal_scores_scam_high_and_normal_low(basal_up):
    basal = BasalBackend(BASAL_URL, timeout=15)
    scam = await basal.assess(DecisionRequest("live", "pl", SCAM_PL))
    normal = await basal.assess(DecisionRequest("live", "pl", NORMAL_PL))
    full = await basal.assess(DecisionRequest("live", "pl", SCAM_PL, full=True))
    await basal.aclose()
    assert scam["risk"] >= 90 and scam["scam_type"] in ("police", "grandchild")
    assert normal["risk"] < 50 and normal["scam_type"] == "none"
    assert full["secrecy"] >= 0.8
