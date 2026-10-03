"""Shared fixtures and fakes. No test talks to the network."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.audio.g711 import mulaw_encode
from app.config import Settings

if TYPE_CHECKING:
    from app.risk.decision import DecisionRequest

BASE_URL = "https://sprawdzam.example.test"
AUTH_TOKEN = "test-auth-token-not-a-real-secret"
ACCOUNT_SID = "AC" + "a" * 32
CALL_SID = "CA" + "1" * 32
STREAM_SID = "MZ" + "2" * 32


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make tests independent of the developer's shell environment."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def make_settings(tmp_path) -> Callable[..., Settings]:
    def _make(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "PUBLIC_BASE_URL": BASE_URL,
            "TWILIO_AUTH_TOKEN": AUTH_TOKEN,
            "TWILIO_ACCOUNT_SID": ACCOUNT_SID,
            "TWILIO_NUMBER": "+48100000000",
            "DATA_DIR": str(tmp_path / "data"),
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return _make


# ---------------------------------------------------------------------------- fakes
class FakeSTT:
    """Returns scripted texts, one per call (the last one repeats)."""

    name = "fake"

    def __init__(self, texts: list[str] | None = None) -> None:
        self.texts = texts or [""]
        self.calls: list[tuple[int, int, str, np.dtype]] = []

    async def transcribe(self, audio: np.ndarray, sample_rate: int, lang: str) -> str:
        self.calls.append((audio.size, sample_rate, lang, audio.dtype))
        return self.texts[min(len(self.calls) - 1, len(self.texts) - 1)]


class FakeDecision:
    """Decision backend returning a fixed payload, raising, or sleeping."""

    name = "fake-decision"

    def __init__(
        self,
        result: Any = None,
        exc: BaseException | None = None,
        delay: float = 0.0,
    ) -> None:
        self.result = result
        self.exc = exc
        self.delay = delay
        self.requests: list[DecisionRequest] = []

    async def assess(self, request: DecisionRequest) -> Mapping[str, Any]:
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc is not None:
            raise self.exc
        return self.result


class RecordingActions:
    """Inner CallActions that records what would have been sent to Twilio."""

    def __init__(self, fail: set[str] | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fail = fail or set()

    async def _record(self, *entry: str) -> None:
        self.calls.append(entry)
        if entry[0] in self.fail:
            raise RuntimeError("simulated Twilio failure")

    async def warn(self, call_sid: str, assessment: Any) -> None:
        await self._record("warn", call_sid)

    async def hang_up(self, call_sid: str) -> None:
        await self._record("hang_up", call_sid)

    async def call_trusted_person(self, call_sid: str, to: str, message: str) -> None:
        await self._record("call", call_sid, to)

    async def send_sms(self, call_sid: str, to: str, body: str) -> None:
        await self._record("sms", call_sid, to)

    def kinds(self) -> list[str]:
        return [entry[0] for entry in self.calls]


# ---------------------------------------------------------------------------- helpers
def twilio_signature(url: str, params: Mapping[str, str], token: str = AUTH_TOKEN) -> str:
    return RequestValidator(token).compute_signature(url, params)


def voice_params(call_sid: str = CALL_SID, **extra: str) -> dict[str, str]:
    params = {
        "CallSid": call_sid,
        "AccountSid": ACCOUNT_SID,
        "From": "+48500000001",
        "To": "+48100000000",
        "CallStatus": "ringing",
        "Direction": "inbound",
    }
    params.update(extra)
    return params


def post_voice(client: TestClient, params: Mapping[str, str], signature: str | None = "auto"):
    headers = {}
    if signature == "auto":
        headers["X-Twilio-Signature"] = twilio_signature(f"{BASE_URL}/twilio/voice", params)
    elif signature is not None:
        headers["X-Twilio-Signature"] = signature
    return client.post("/twilio/voice", data=dict(params), headers=headers)


def tone_mulaw_frames(seconds: float, freq: float = 1000.0, amplitude: float = 0.3) -> list[str]:
    """Base64 mu-law 20 ms frames of a sine tone at 8 kHz (what Twilio would send)."""
    n = int(seconds * 8000)
    t = np.arange(n) / 8000.0
    mulaw = mulaw_encode((amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32))
    return [base64.b64encode(mulaw[i : i + 160]).decode() for i in range(0, n, 160)]


@pytest.fixture
def make_client(make_settings):
    """Build a TestClient around an app wired with fakes."""
    clients: list[TestClient] = []

    from app.factory import create_app

    def _make(settings: Settings | None = None, **kwargs: Any) -> TestClient:
        app = create_app(settings or make_settings(), **kwargs)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)
