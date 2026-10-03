"""Fake backend for protocol v0 (dev only). SILENT: sends only zero PCM frames to the app.

Run:  uv run --with websockets python tools/fake_backend.py [--port 8765] [--call-after 5] [--end-after 0]
Then: hdc -t 127.0.0.1:5555 rport tcp:8765 tcp:8765
"""
import argparse
import asyncio
import json
import math
import struct
import time

from websockets.asyncio.server import serve

FRAME = bytes(640)  # 20 ms of silence, PCM16 LE mono 16 kHz
CALLS: dict[str, str] = {}
ARGS = None


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


async def control(ws, token):
    log(f"control: connected device_token={token!r}")
    await ws.send(json.dumps({"type": "protection_status", "available": True}))

    async def announce():
        await asyncio.sleep(ARGS.call_after)
        call_id = f"test-{int(time.time())}"
        CALLS[call_id] = "tok-" + call_id
        msg = {"type": "incoming_call", "callId": call_id, "token": CALLS[call_id],
               "caller": "+48 600 000 000", "lang": "pl"}
        log("control: ->", msg)
        await ws.send(json.dumps(msg))

    task = asyncio.create_task(announce()) if ARGS.call_after >= 0 else None
    try:
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "ping":
                await ws.send(json.dumps({"type": "pong"}))
                log("control: ping -> pong")
            else:
                log("control: <-", msg)
    finally:
        if task:
            task.cancel()
        log("control: closed")


async def call(ws, call_id, token):
    if CALLS.get(call_id) != token:
        log(f"call {call_id}: bad token {token!r}")
        await ws.close(4001, "bad token")
        return
    log(f"call {call_id}: connected")
    received = 0
    window = bytearray()
    accepted = asyncio.Event()
    started = time.monotonic()

    async def sender():
        await accepted.wait()
        t0 = time.monotonic()
        n = 0
        script = [
            (3, {"type": "risk", "score": 20, "level": "none", "scamType": "none", "reasons": []}),
            (6, {"type": "risk", "score": 62, "level": "warn", "scamType": "grandchild",
                 "reasons": ["asks for money", "urgency"]}),
            (9, {"type": "risk", "score": 88, "level": "high", "scamType": "grandchild",
                 "reasons": ["asks for money", "secrecy", "urgency"]}),
            (9.5, {"type": "verify_password"}),
        ]
        while True:
            await ws.send(FRAME)
            n += 1
            elapsed = time.monotonic() - t0
            while script and elapsed >= script[0][0]:
                _, msg = script.pop(0)
                log(f"call {call_id}: ->", msg)
                await ws.send(json.dumps(msg))
            if ARGS.end_after > 0 and elapsed >= ARGS.end_after:
                msg = {"type": "call_ended", "reason": "remote_hangup"}
                log(f"call {call_id}: ->", msg)
                await ws.send(json.dumps(msg))
                await ws.close()
                return
            await asyncio.sleep(max(0, t0 + n * 0.02 - time.monotonic()))

    task = asyncio.create_task(sender())
    try:
        async for raw in ws:
            if isinstance(raw, bytes):
                received += len(raw)
                window.extend(raw)
                if len(window) >= 32000:  # 1 s of app audio
                    samples = struct.unpack(f"<{len(window) // 2}h", window[: len(window) // 2 * 2])
                    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
                    log(f"call {call_id}: app audio {received} bytes total, last 1 s rms={rms:.0f}")
                    window.clear()
            else:
                msg = json.loads(raw)
                log(f"call {call_id}: <-", msg)
                if msg.get("type") == "accept":
                    accepted.set()
                elif msg.get("type") == "hangup":
                    break
    finally:
        task.cancel()
        log(f"call {call_id}: closed after {time.monotonic() - started:.1f}s, app audio {received} bytes")


async def handler(ws):
    path = ws.request.path
    route, _, query = path.partition("?")
    params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
    if route == "/app/control":
        await control(ws, params.get("device_token", ""))
    elif route.startswith("/app/call/"):
        await call(ws, route[len("/app/call/"):], params.get("token", ""))
    else:
        log("unknown path", path)
        await ws.close(4004, "not found")


async def main():
    async with serve(handler, "127.0.0.1", ARGS.port, max_size=2**20):
        log(f"fake backend on ws://127.0.0.1:{ARGS.port}")
        await asyncio.Future()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--call-after", type=float, default=5, help="seconds after control connect; -1 = never")
    p.add_argument("--end-after", type=float, default=0, help="seconds after accept to send call_ended; 0 = never")
    ARGS = p.parse_args()
    asyncio.run(main())
