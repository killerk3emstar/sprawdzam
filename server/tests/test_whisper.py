import io
import wave

import httpx
import numpy as np
import pytest

from app.stt.base import STTError
from app.stt.whisper import WhisperSTT, extract_text, is_hallucination

pytestmark = pytest.mark.anyio


def client_with(handler) -> WhisperSTT:
    return WhisperSTT(
        "http://whisper.test",
        timeout=0.5,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def segment(text: str, no_speech: float = 0.0) -> dict:
    return {"id": 0, "text": text, "avg_logprob": -0.1, "no_speech_prob": no_speech}


async def test_sends_wav_with_forced_language_and_strips_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "text": " Dzień dobry, tu aspirant Kowalski.\n",
                "segments": [segment(" Dzień dobry, tu aspirant Kowalski.\n")],
            },
        )

    stt = client_with(handler)
    audio = (0.1 * np.sin(np.arange(16000) / 5)).astype(np.float32)
    text = await stt.transcribe(audio, 16000, "pl")
    assert text == "Dzień dobry, tu aspirant Kowalski."
    assert seen["url"] == "http://whisper.test/inference"
    body = seen["body"]
    for field, value in [
        (b"language", b"pl"),
        (b"response_format", b"verbose_json"),
        (b"temperature", b"0.0"),
    ]:
        assert b'name="' + field + b'"\r\n\r\n' + value in body
    wav_bytes = body[body.index(b"RIFF") :]
    with wave.open(io.BytesIO(wav_bytes)) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        assert wav.getnframes() == 16000


async def test_drops_no_speech_and_hallucinated_segments():
    payload = {
        "segments": [
            segment(" Proszę nikomu nie mówić.", 0.01),
            segment(" KONIEC", 0.2),
            segment(" Napisy wykonane przez społeczność Amara.org", 0.1),
            segment(" to zabrzmi dziwnie", 0.95),
            segment(" Dziękuję za uwagę.", 0.1),
        ]
    }
    assert extract_text(payload) == "Proszę nikomu nie mówić."
    assert extract_text({"text": " Thank you for watching!\n"}) == ""


@pytest.mark.parametrize(
    "text",
    [
        "KONIEC",
        "Koniec.",
        "Dziękuję za uwagę!",
        "Thank you.",
        "Thanks for watching",
        "Napisy stworzone przez XYZ",
        "...",
        "",
    ],
)
def test_hallucination_filter(text):
    assert is_hallucination(text)


@pytest.mark.parametrize(
    "text", ["Koniec rozmowy, proszę przelać pieniądze", "Thank you, I will transfer the money"]
)
def test_real_sentences_are_kept(text):
    assert not is_hallucination(text)


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(500, text="boom"), "HTTP 500"),
        (httpx.Response(200, text="not json"), "invalid JSON"),
        (httpx.Response(200, json=[1, 2]), "unexpected response shape"),
        (httpx.Response(200, json={"segments": "x"}), "segments is not a list"),
        (httpx.Response(200, json={"segments": [{"no_text": 1}]}), "malformed segment"),
        (httpx.Response(200, json={"foo": 1}), "neither segments nor text"),
    ],
)
async def test_errors_raise_stt_error(response, reason):
    stt = client_with(lambda request: response)
    with pytest.raises(STTError, match=reason):
        await stt.transcribe(np.zeros(1600, dtype=np.float32), 16000, "en")


async def test_timeout_and_connection_errors():
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(STTError, match="timeout"):
        await client_with(slow).transcribe(np.zeros(160, dtype=np.float32), 16000, "pl")

    def down(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(STTError, match="transport error"):
        await client_with(down).transcribe(np.zeros(160, dtype=np.float32), 16000, "pl")
