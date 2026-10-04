"""End-to-end smoke test of one protected call against a running backend (DEV_TOOLS=true).

Plays both sides with Python clients:
* the senior app (protocol v0): control channel, call channel, `accept`, collects events;
* the caller: `POST /dev/calls`, then the provider media stream (Twilio format) fed with a
  WAV file in real time (8 kHz mu-law WAV is sent as is; PCM WAV is converted).

Prints a timeline (seconds from the stream start) of risk events, verify_password and
call_ended, and how much prompt audio the caller received. `--audio` also takes the raw
`.ulaw` clips from `make_samples.sh`. Usage (from `server/`):

    APP_DEVICE_TOKEN=... uv run python scripts/smoke_call.py \\
        --audio ~/models/sprawdzam/audio/pl_scam_police_8k_ulaw.wav --lang pl
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import json
import os
import struct
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audio.g711 import mulaw_encode  # noqa: E402
from app.audio.resample import resample  # noqa: E402

STREAM_SID = "MZ" + "7" * 32
SILENCE = base64.b64encode(b"\xff" * 160).decode()


def read_wav_as_mulaw(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix == ".ulaw":
        return data  # raw 8 kHz mu-law, as rendered by make_samples.sh
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise SystemExit(f"{path}: not a WAV file")
    pos, fmt, audio = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos : pos + 4], struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        body = data[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif cid == b"data":
            audio = body
        pos += 8 + size + (size % 2)
    if fmt is None or audio is None:
        raise SystemExit(f"{path}: missing fmt or data chunk")
    tag, channels, rate, _, _, bits = fmt
    if channels != 1:
        raise SystemExit(f"{path}: mono audio required")
    if tag == 7 and rate == 8000:
        return audio  # already what a phone network sends
    if tag == 1 and bits == 16:
        pcm = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768
        return mulaw_encode(resample(pcm, rate, 8000))
    raise SystemExit(f"{path}: unsupported WAV format tag={tag} bits={bits}")


async def run(args: argparse.Namespace) -> dict:
    base = args.base.rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    audio = read_wav_as_mulaw(args.audio)
    timeline: list[dict] = []
    result: dict = {"audio": str(args.audio), "audio_seconds": round(len(audio) / 8000, 1)}

    async with websockets.connect(
        f"{ws_base}/app/control?device_token={args.device_token}"
    ) as control:
        status = json.loads(await control.recv())
        assert status == {"type": "protection_status", "available": True}, status
        async with httpx.AsyncClient() as http:
            response = await http.post(
                f"{base}/dev/calls", json={"caller": args.caller, "lang": args.lang}
            )
        response.raise_for_status()
        call = response.json()
        async with websockets.connect(f"{ws_base}{call['streamPath']}") as stream:
            await stream.send(json.dumps({"event": "connected", "protocol": "Call"}))
            await stream.send(
                json.dumps(
                    {
                        "event": "start",
                        "streamSid": STREAM_SID,
                        "start": {
                            "streamSid": STREAM_SID,
                            "callSid": call["callId"],
                            "customParameters": {"token": call["token"], "lang": call["lang"]},
                            "mediaFormat": {
                                "encoding": "audio/x-mulaw",
                                "sampleRate": 8000,
                                "channels": 1,
                            },
                        },
                    }
                )
            )
            t0 = time.monotonic()
            incoming = json.loads(await control.recv())
            url = f"{ws_base}/app/call/{incoming['callId']}?token={incoming['token']}"
            async with websockets.connect(url) as app:
                await app.send(json.dumps({"type": "accept"}))
                ended = asyncio.Event()
                counters = {
                    "app_audio_frames": 0,
                    "caller_media_after_answer": 0,
                    "caller_clears": 0,
                }

                async def app_events() -> None:
                    async for message in app:
                        if isinstance(message, bytes):
                            counters["app_audio_frames"] += 1
                            continue
                        event = json.loads(message)
                        event["t"] = round(time.monotonic() - t0, 1)
                        timeline.append(event)
                        print(json.dumps(event, ensure_ascii=False), flush=True)
                        if event["type"] == "call_ended":
                            ended.set()
                            return

                async def caller_side() -> None:
                    async for message in stream:
                        event = json.loads(message)
                        if event["event"] == "clear":
                            counters["caller_clears"] += 1
                        elif event["event"] == "media" and counters["caller_clears"]:
                            counters["caller_media_after_answer"] += 1

                async def feed() -> None:
                    frames = [
                        base64.b64encode(audio[i : i + 160]).decode()
                        for i in range(0, len(audio), 160)
                    ]
                    frames += [SILENCE] * int(args.tail_seconds / 0.02)
                    start = time.monotonic()
                    for i, payload in enumerate(frames):
                        if ended.is_set():
                            return
                        await stream.send(
                            json.dumps(
                                {
                                    "event": "media",
                                    "streamSid": STREAM_SID,
                                    "media": {"track": "inbound", "payload": payload},
                                }
                            )
                        )
                        delay = start + (i + 1) * 0.02 - time.monotonic()
                        if delay > 0:
                            await asyncio.sleep(delay)
                    await stream.send(json.dumps({"event": "stop", "streamSid": STREAM_SID}))

                tasks = [asyncio.create_task(c()) for c in (app_events, caller_side, feed)]
                with contextlib.suppress(TimeoutError, websockets.ConnectionClosed):
                    await asyncio.wait_for(tasks[0], args.audio_timeout + len(audio) / 8000)
                for task in tasks:
                    task.cancel()
                result.update(counters)
    result["timeline"] = timeline
    risks = [e for e in timeline if e["type"] == "risk"]
    first = lambda pred: next((e["t"] for e in timeline if pred(e)), None)  # noqa: E731
    result["summary"] = {
        "max_score": max((e["score"] for e in risks), default=0),
        "first_warn_s": first(lambda e: e["type"] == "risk" and e["level"] == "warn"),
        "first_high_s": first(lambda e: e["type"] == "risk" and e["level"] == "high"),
        "verify_password_s": first(lambda e: e["type"] == "verify_password"),
        "call_ended": next(
            ({"t": e["t"], "reason": e["reason"]} for e in timeline if e["type"] == "call_ended"),
            None,
        ),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="End-to-end smoke test of one call")
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--device-token", default=os.environ.get("APP_DEVICE_TOKEN", ""))
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--lang", choices=["pl", "en"], default="pl")
    parser.add_argument("--caller", default="+48500000123")
    parser.add_argument(
        "--tail-seconds",
        type=float,
        default=30.0,
        help="silence streamed after the clip (keeps the call open)",
    )
    parser.add_argument("--audio-timeout", type=float, default=40.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not args.device_token:
        raise SystemExit("set APP_DEVICE_TOKEN or --device-token")
    result = asyncio.run(run(args))
    print(json.dumps(result["summary"], ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k not in ("timeline", "summary")}))
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
