"""Fake backend implementing APP_PROTOCOL.md v0 (server repo, docs/APP_PROTOCOL.md) for local app tests.

SILENT: it only ever sends zero PCM frames, so nothing is audible on the device.

Run:  uv run --with websockets python tools/fake_backend.py [options]
Then: hdc -t 127.0.0.1:5555 rport tcp:8765 tcp:8765

Behaviour (as in the real backend):
- control: wrong device token -> close 1008; protection_status on connect; pong for ping; close 4000 after 45 s
  without messages; incoming_call `--call-after` seconds after connect (masked caller, token valid 5 min, single use)
- call: wrong/used/expired token or ended call -> close 1008; no audio before accept; no accept within 30 s ->
  call_ended(timeout); hangup -> call_ended(senior_hangup); call_ended is followed by close 1000
- scenario "scam": risk none/warn/high, then verify_password; the correct `--password` via dtmf within 20 s lets
  the call continue, otherwise call_ended(scam_blocked). "benign": low risk only. `--caller-hangup N`: caller hangs
  up N s after accept.
"""
import argparse
import asyncio
import json
import math
import secrets
import struct
import time
from urllib.parse import parse_qs

from websockets.asyncio.server import serve

FRAME = bytes(640)  # 20 ms of silence, PCM16 LE mono 16 kHz
CONTROL_IDLE_S = 45
TOKEN_TTL_S = 300
ACCEPT_TIMEOUT_S = 30
PASSWORD_TIMEOUT_S = 20
CALLS: dict[str, dict] = {}  # callId -> {"token", "created", "used", "ended"}
ARGS: argparse.Namespace


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


async def control(ws, device_token):
    if ARGS.device_token and device_token != ARGS.device_token:
        log("control: bad device token -> 1008")
        await ws.close(1008, "bad device token")
        return
    log("control: connected")
    await ws.send(json.dumps({"type": "protection_status", "available": True}))

    async def announce():
        await asyncio.sleep(ARGS.call_after)
        call_id = f"CA{secrets.token_hex(8)}"
        CALLS[call_id] = {"token": secrets.token_urlsafe(16), "created": time.monotonic(), "used": False,
                          "ended": False}
        msg = {"type": "incoming_call", "callId": call_id, "token": CALLS[call_id]["token"],
               "caller": "+48 *** *** 123", "lang": ARGS.lang}
        log("control: -> incoming_call", call_id)
        await ws.send(json.dumps(msg))

    task = asyncio.create_task(announce()) if ARGS.call_after >= 0 else None
    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=ARGS.idle)
            except asyncio.TimeoutError:
                log(f"control: idle for {ARGS.idle}s -> 4000")
                await ws.close(4000, "idle")
                return
            try:
                msg = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if msg.get("type") == "ping":
                await ws.send(json.dumps({"type": "pong"}))
                log("control: ping -> pong")
            elif msg.get("type") == "settings":
                # Personal data: log only the shape, never names or numbers.
                tp = msg.get("trustedPerson") or {}
                log(f"control: <- settings lang={msg.get('lang')} trustedPerson={'set' if tp.get('number') else 'none'}"
                    f" whitelist={len(msg.get('whitelist') or [])} numbers")
            else:
                log("control: <-", msg.get("type"))
    except Exception as e:  # connection closed by the app
        log("control: closed", type(e).__name__)
    finally:
        if task:
            task.cancel()


async def call(ws, call_id, token):
    info = CALLS.get(call_id)
    if (info is None or info["token"] != token or info["used"] or info["ended"]
            or time.monotonic() - info["created"] > TOKEN_TTL_S):
        log(f"call {call_id}: rejected token -> 1008")
        await ws.close(1008, "bad token")
        return
    info["used"] = True
    log(f"call {call_id}: connected (ringing)")
    state = {"accepted": False, "password_ok": False, "verify_at": None, "ended": False}
    received = 0
    window = bytearray()
    accepted = asyncio.Event()
    dtmf_ok = asyncio.Event()

    async def end(reason):
        if state["ended"]:
            return
        state["ended"] = True
        info["ended"] = True
        log(f"call {call_id}: -> call_ended {reason}")
        try:
            await ws.send(json.dumps({"type": "call_ended", "reason": reason}))
            await ws.close(1000)
        except Exception:
            pass

    async def send_json(msg):
        log(f"call {call_id}: ->", msg)
        await ws.send(json.dumps(msg))

    async def driver():
        try:
            await asyncio.wait_for(accepted.wait(), timeout=ACCEPT_TIMEOUT_S)
        except asyncio.TimeoutError:
            await end("timeout")
            return
        if ARGS.scenario == "scam":
            script = [
                (3, {"type": "risk", "score": 18, "level": "none", "scamType": "none", "reasons": ["money"]}),
                (6, {"type": "risk", "score": 64, "level": "warn", "scamType": "police",
                     "reasons": ["authority", "money"]}),
                (9, {"type": "risk", "score": 93, "level": "high", "scamType": "police",
                     "reasons": ["authority", "money", "secrecy"]}),
                (9.5, {"type": "verify_password"}),
            ]
        else:
            script = [(3, {"type": "risk", "score": 10, "level": "none", "scamType": "none", "reasons": []}),
                      (7, {"type": "risk", "score": 12, "level": "none", "scamType": "none", "reasons": []})]
        t0 = time.monotonic()
        n = 0
        while not state["ended"]:
            await ws.send(FRAME)
            n += 1
            elapsed = time.monotonic() - t0
            while script and elapsed >= script[0][0]:
                _, msg = script.pop(0)
                await send_json(msg)
                if msg["type"] == "verify_password":
                    state["verify_at"] = time.monotonic()
            if state["verify_at"] and not state["password_ok"]:
                if dtmf_ok.is_set():
                    state["password_ok"] = True
                    log(f"call {call_id}: family password OK, call continues")
                elif time.monotonic() - state["verify_at"] > ARGS.password_timeout:
                    await end("scam_blocked")
                    return
            if ARGS.caller_hangup > 0 and elapsed >= ARGS.caller_hangup:
                await end("caller_hangup")
                return
            await asyncio.sleep(max(0, t0 + n * 0.02 - time.monotonic()))

    task = asyncio.create_task(driver())
    started = time.monotonic()
    try:
        async for raw in ws:
            if isinstance(raw, bytes):
                if not state["accepted"] or len(raw) % 2 or len(raw) > 6400:
                    continue  # no audio before accept; odd or oversized frames are dropped
                received += len(raw)
                window.extend(raw)
                if len(window) >= 32000:  # 1 s of app audio
                    samples = struct.unpack(f"<{len(window) // 2}h", bytes(window))
                    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
                    log(f"call {call_id}: app audio {received} bytes total, last 1 s rms={rms:.0f}")
                    window.clear()
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            kind = msg.get("type")
            if kind == "accept" and not state["accepted"]:
                state["accepted"] = True
                log(f"call {call_id}: <- accept")
                accepted.set()
            elif kind == "hangup":
                log(f"call {call_id}: <- hangup")
                await end("senior_hangup")
                break
            elif kind == "dtmf":
                digits = str(msg.get("digits", ""))
                log(f"call {call_id}: <- dtmf ({len(digits)} digits)")
                if state["verify_at"] and digits == ARGS.password:
                    dtmf_ok.set()
    except Exception as e:
        log(f"call {call_id}: socket error {type(e).__name__}")
    finally:
        task.cancel()
        if not state["ended"]:
            info["ended"] = True
            log(f"call {call_id}: channel dropped -> call ends with error")
        log(f"call {call_id}: closed after {time.monotonic() - started:.1f}s, app audio {received} bytes")


async def handler(ws):
    route, _, query = ws.request.path.partition("?")
    params = {k: v[0] for k, v in parse_qs(query).items()}
    if route == "/app/control":
        await control(ws, params.get("device_token", ""))
    elif route.startswith("/app/call/"):
        await call(ws, route[len("/app/call/"):], params.get("token", ""))
    else:
        log("unknown path", route)
        await ws.close(1008, "not found")


async def main():
    async with serve(handler, "127.0.0.1", ARGS.port, max_size=2**20):
        log(f"fake backend on ws://127.0.0.1:{ARGS.port} scenario={ARGS.scenario}")
        await asyncio.Future()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--device-token", default="", help="expected device token; empty = accept any")
    p.add_argument("--call-after", type=float, default=5, help="seconds after control connect; -1 = never")
    p.add_argument("--scenario", choices=["scam", "benign"], default="scam")
    p.add_argument("--password", default="1234", help="family password expected via dtmf")
    p.add_argument("--password-timeout", type=float, default=PASSWORD_TIMEOUT_S)
    p.add_argument("--caller-hangup", type=float, default=0, help="caller hangs up N s after accept; 0 = never")
    p.add_argument("--idle", type=float, default=CONTROL_IDLE_S, help="control idle close (4000) after N s")
    p.add_argument("--lang", default="pl")
    ARGS = p.parse_args()
    asyncio.run(main())
