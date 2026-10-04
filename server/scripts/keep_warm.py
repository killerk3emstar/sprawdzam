"""Keep the model servers resident in memory between demo calls.

On a Mac under memory pressure macOS pages idle model weights out; the first call after a long
pause then sees Whisper and basal time out for ~50 s while the weights page back in (seen on
4 Oct: 1.5 h idle, 36 GB swapped). This sends one tiny request to each model every
`--every` seconds, but only while no call is active (checked on the backend's /health).

    uv run python scripts/keep_warm.py [--every 30] [--backend http://127.0.0.1:8765]

Started by scripts/demo-up.sh. Reads model URLs from the same settings as the backend.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.factory import build_decision_backend, build_stt  # noqa: E402


async def active_calls(client: httpx.AsyncClient, backend: str) -> int:
    try:
        health = (await client.get(f"{backend}/health", timeout=3)).json()
        calls = health.get("calls", {})
        return int(calls.get("active", 0)) + int(calls.get("pending", 0))
    except Exception:  # noqa: BLE001 - backend down: still keep the models warm
        return 0


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--every", type=float, default=30.0)
    parser.add_argument("--backend", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    settings = Settings()
    models = {"stt": build_stt(settings), "decision": build_decision_backend(settings)}
    async with httpx.AsyncClient() as client:
        while True:
            if await active_calls(client, args.backend) == 0:
                for name, model in models.items():
                    if model is None or not hasattr(model, "warm_up"):
                        continue
                    started = time.strftime("%H:%M:%S")
                    try:
                        ms = await asyncio.wait_for(model.warm_up(), 60)
                        print(f"{started} {name} {ms:.0f} ms", flush=True)
                    except Exception as exc:  # noqa: BLE001
                        print(f"{started} {name} failed: {type(exc).__name__}", flush=True)
            await asyncio.sleep(args.every)


if __name__ == "__main__":
    asyncio.run(main())
