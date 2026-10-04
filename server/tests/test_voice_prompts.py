import logging

import numpy as np

from app.audio.g711 import mulaw_encode
from app.calls.voice_prompts import PromptLibrary
from tests.conftest import (
    FakeSTT,
    admit,
    drain_until_close,
    media,
    receive_json,
    scam_model,
    speech_mulaw_frames,
    start_message,
    wait_until,
)

SCAM_TEXT = (
    "Mówi komisarz z CBŚ. Proszę wypłacić gotówkę i przekazać ją kurierowi. Nikomu o tym nie mówić."
)


def write_prompt(directory, name: str, lang: str, seconds: float, freq: float) -> bytes:
    t = np.arange(int(seconds * 8000)) / 8000
    data = mulaw_encode((0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}_{lang}.ulaw").write_bytes(data)
    return data


def test_library_loads_frames_and_reports_missing(tmp_path, caplog):
    write_prompt(tmp_path, "warning", "pl", 1.0, 500)
    library = PromptLibrary(tmp_path)
    phone = library.phone_frames("warning", "pl")
    app = library.app_frames("warning", "pl")
    assert len(phone) == 50 and all(len(f) == 160 for f in phone)
    assert len(app) == 50 and all(len(f) == 640 for f in app)
    assert library.phone_frames("password", "en") is None
    assert library.app_frames("password", "en") is None
    missing = [r for r in caplog.records if "voice_prompt_missing" in r.getMessage()]
    assert len(missing) == 1  # logged once per prompt
    status = library.status()
    assert status["warning_pl"] is True and status["blocked_en"] is False


def test_library_rejects_empty_and_huge_files(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    (tmp_path / "blocked_pl.ulaw").write_bytes(b"")
    (tmp_path / "password_pl.ulaw").write_bytes(b"\xff" * (8000 * 31))
    library = PromptLibrary(tmp_path)
    assert library.phone_frames("blocked", "pl") is None
    assert library.phone_frames("password", "pl") is None


def test_prompts_are_played_during_password_check(make_client, make_settings, tmp_path):
    prompt_dir = tmp_path / "data" / "prompts"
    password = write_prompt(prompt_dir, "password", "pl", 0.4, 700)
    blocked = write_prompt(prompt_dir, "blocked", "pl", 0.3, 900)
    write_prompt(prompt_dir, "warning", "pl", 0.3, 600)
    settings = make_settings(FAMILY_PASSWORD="2468", VERIFY_PASSWORD_SECONDS=0.3)
    client = make_client(settings, stt=FakeSTT([SCAM_TEXT]), decision_backend=scam_model())
    with client.websocket_connect("/twilio/stream") as stream:
        stream.send_json(start_message(admit(client)))
        assert wait_until(lambda: client.control.of_type("incoming_call"))
        incoming = client.control.of_type("incoming_call")[0]
        url = f"/app/call/{incoming['callId']}?token={incoming['token']}"
        with client.websocket_connect(url) as app_ws:
            app_ws.send_json({"type": "accept"})
            for payload in speech_mulaw_frames():
                stream.send_json(media(payload))
            assert receive_json(app_ws, "call_ended")["reason"] == "scam_blocked"
        messages, _ = drain_until_close(stream)
    # After the answer (`clear`), the caller hears the password prompt and then the
    # blocked notice, each preceded by a `clear`.
    after_answer = messages[[m["event"] for m in messages].index("clear") + 1 :]
    clears = [i for i, m in enumerate(after_answer) if m["event"] == "clear"]
    assert len(clears) == 2
    played = [m for m in after_answer if m["event"] == "media"]
    assert len(played) == len(password) // 160 + len(blocked) // 160
