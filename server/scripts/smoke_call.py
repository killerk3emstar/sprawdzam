"""End-to-end smoke test of one protected call against a running backend (DEV_TOOLS=true).

Plays both sides with Python clients:
* the senior app (protocol v0): control channel, call channel, `accept`, collects events;
* the caller: `POST /dev/calls`, then the provider media stream (Twilio format) fed with a
  WAV file in real time (8 kHz mu-law WAV is sent as is; PCM WAV is converted).

Prints a timeline (seconds from the stream start) of risk events, verify_password and
call_ended, and how much prompt audio the caller received. It also:
* subscribes to `WS /dev/events` (the jury / operator console stream) and summarises it;
* answers `alert_trusted` on the control channel with `alert_trusted_result` (sent: true)
  and counts how many alerts arrived (expected: exactly one for a blocked call);
* with `--senior-audio WAV` streams that clip as the senior's microphone, starting
  `--senior-at` seconds after the answer (real senior speech for the transcript);
* with `--echo-gain G` plays the caller audio the app receives back into the call as the
  senior's microphone at gain G (a speaker-to-mic leak), to exercise the echo guard.
Usage (from `server/`):

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

from app.audio.g711 import mulaw_decode, mulaw_encode  # noqa: E402
from app.audio.resample import resample  # noqa: E402

STREAM_SID = "MZ" + "7" * 32
SILENCE = base64.b64encode(b"\xff" * 160).decode()


def read_wav_as_mulaw(path: Path) -> bytes:
    data = path.read_bytes()
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


async def collect_events(ws_base: str, sink: list[dict], stop: asyncio.Event) -> None:
    with contextlib.suppress(Exception):
        async with websockets.connect(f"{ws_base}/dev/events") as events:
            while not stop.is_set():
                with contextlib.suppress(TimeoutError):
                    sink.append(json.loads(await asyncio.wait_for(events.recv(), 0.5)))


def summarise_events(events: list[dict], call_id: str) -> dict:
    mine = [e for e in events if e.get("callId") == call_id]
    kinds: dict[str, int] = {}
    for event in mine:
        kinds[event["type"]] = kinds.get(event["type"], 0) + 1
    speakers: dict[str, int] = {}
    for event in mine:
        if event["type"] == "transcript":
            speakers[event["speaker"]] = speakers.get(event["speaker"], 0) + 1
    ended = next((e for e in mine if e["type"] == "call_ended"), None)
    return {
        "hello": bool(events) and events[0].get("type") == "hello",
        "counts": kinds,
        "transcript_speakers": speakers,
        "actions": [e["action"] for e in mine if e["type"] == "action"],
        "risk_sources": sorted({e["source"] for e in mine if e["type"] == "risk"}),
        "call_ended_reason": ended and ended["reason"],
        "alert": ended and ended["alert"],
    }


async def run(args: argparse.Namespace) -> dict:
    base = args.base.rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    events: list[dict] = []
    stop_events = asyncio.Event()
    collector = asyncio.create_task(collect_events(ws_base, events, stop_events))
    await asyncio.sleep(0.3)
    try:
        result = await run_call(args, base, ws_base)
    finally:
        await asyncio.sleep(1.0)  # late actions (sms_sent)
        stop_events.set()
        await collector
    result["events"] = events
    call_ids = [e["callId"] for e in events if e.get("type") == "call_started"]
    result["events_summary"] = summarise_events(events, call_ids[-1]) if call_ids else {}
    return result


async def run_call(args: argparse.Namespace, base: str, ws_base: str) -> dict:
    audio = read_wav_as_mulaw(args.audio)
    timeline: list[dict] = []
    result: dict = {"audio": str(args.audio), "audio_seconds": round(len(audio) / 8000, 1)}

    async with websockets.connect(
        f"{ws_base}/app/control?device_token={args.device_token}"
    ) as control:
        status = json.loads(await control.recv())
        assert status == {"type": "protection_status", "available": True}, status

        async def pinger() -> None:  # the backend closes an idle control channel after 45 s
            with contextlib.suppress(websockets.ConnectionClosed):
                while True:
                    await asyncio.sleep(15)
                    await control.send(json.dumps({"type": "ping"}))

        ping_task = asyncio.create_task(pinger())
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
            incoming = {}
            while incoming.get("type") != "incoming_call":
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
                            if args.echo_gain > 0 and not ended.is_set():
                                pcm = np.frombuffer(message, dtype="<i2").astype(np.float32)
                                leak = np.clip(pcm * args.echo_gain, -32768, 32767)
                                with contextlib.suppress(websockets.ConnectionClosed):
                                    await app.send(leak.astype("<i2").tobytes())
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

                async def senior_side() -> None:
                    if args.senior_audio is None:
                        return
                    mulaw = read_wav_as_mulaw(args.senior_audio)
                    pcm8k = mulaw_decode(mulaw).astype(np.float32) / 32768
                    pcm = (resample(pcm8k, 8000, 16000) * 32767).astype("<i2").tobytes()
                    await asyncio.sleep(args.senior_at)
                    start = time.monotonic()
                    for i in range(0, len(pcm), 640):
                        if ended.is_set():
                            return
                        await app.send(pcm[i : i + 640])
                        delay = start + (i // 640 + 1) * 0.02 - time.monotonic()
                        if delay > 0:
                            await asyncio.sleep(delay)

                tasks = [
                    asyncio.create_task(c()) for c in (app_events, caller_side, feed, senior_side)
                ]
                with contextlib.suppress(TimeoutError, websockets.ConnectionClosed):
                    await asyncio.wait_for(tasks[0], args.audio_timeout + len(audio) / 8000)
                for task in tasks:
                    task.cancel()
                result.update(counters)
        # The trusted-person alert arrives on the control channel after the call ends.
        alerts: list[dict] = []
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(args.alert_wait):
                while True:
                    message = json.loads(await control.recv())
                    if message.get("type") == "alert_trusted":
                        message["t"] = round(time.monotonic() - t0, 1)
                        alerts.append(message)
                        print(json.dumps(message, ensure_ascii=False), flush=True)
                        await control.send(
                            json.dumps(
                                {
                                    "type": "alert_trusted_result",
                                    "callId": message["callId"],
                                    "sent": True,
                                }
                            )
                        )
        result["alerts_trusted"] = alerts
        ping_task.cancel()
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
    parser.add_argument("--echo-gain", type=float, default=0.0)
    parser.add_argument("--senior-audio", type=Path)
    parser.add_argument("--senior-at", type=float, default=5.0)
    parser.add_argument("--alert-wait", type=float, default=3.0)
    args = parser.parse_args()
    if not args.device_token:
        raise SystemExit("set APP_DEVICE_TOKEN or --device-token")
    result = asyncio.run(run(args))
    print(json.dumps(result["summary"], ensure_ascii=False))
    print(json.dumps(result.get("events_summary", {}), ensure_ascii=False))
    print(f"alert_trusted received: {len(result.get('alerts_trusted', []))}")
    skip = ("timeline", "summary", "events", "events_summary", "alerts_trusted")
    print(json.dumps({k: v for k, v in result.items() if k not in skip}))
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
