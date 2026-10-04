"""Dev-only routes (DEV_TOOLS=true): browser stand-ins for the caller and the senior app.

* `GET /dev/caller`: the "scammer" side. Talks to the real provider media-stream WebSocket
  using the Twilio message format (browser mic -> 8 kHz mu-law -> base64 `media`).
* `GET /dev/senior`: the senior app, speaking app protocol v0 (docs/APP_PROTOCOL.md).
* `GET /dev/jury`: projector console for the jury (live transcript, risk chart, actions) and the
  operator alert table; fed by the `/dev/events` WebSocket, or by a replay with `?mock=1`.
* `GET /dev/`: index of the dev pages.
* `POST /dev/calls`: admits a call exactly like the voice webhook (rate limit, app online,
  concurrency slot, one-time stream token) but without a provider signature.
* `GET /dev/samples`, `GET /dev/samples/{name}.ulaw`: sample caller clips rendered by
  `scripts/make_samples.sh` into `DATA_DIR/samples/` (8 kHz mu-law), streamed by /dev/caller
  instead of the microphone.

Never enable on a public deployment: `POST /dev/calls` bypasses webhook authentication.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.calls.intake import AdmitOutcome, admit_call
from app.config import Lang
from app.prompts import PROTECTION_NOTICE, PROTECTION_UNAVAILABLE
from app.services import get_services

STATIC_DIR = Path(__file__).parent / "static"
NO_STORE = {"Cache-Control": "no-store"}

router = APIRouter(prefix="/dev")
SAMPLE_NAME = re.compile(r"^(pl|en)_[a-z0-9_]{1,40}$")
MAX_SAMPLE_BYTES = 8000 * 120  # 2 minutes


def _samples_dir(request: Request) -> Path:
    return Path(get_services(request).settings.DATA_DIR) / "samples"


class DevCallRequest(BaseModel):
    caller: str = Field(default="+48500000001", pattern=r"^(\+[1-9]\d{6,14})?$")
    lang: Lang | None = None


@router.get("/caller", include_in_schema=False)
async def caller_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "caller.html", headers=NO_STORE)


@router.get("/senior", include_in_schema=False)
async def senior_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "senior.html", headers=NO_STORE)


@router.get("/jury", include_in_schema=False)
async def jury_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "jury.html", headers=NO_STORE)


@router.get("/", include_in_schema=False)
async def index_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers=NO_STORE)


@router.get("/samples")
async def list_samples(request: Request) -> JSONResponse:
    directory = _samples_dir(request)
    samples = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.ulaw")):
            size = path.stat().st_size
            if SAMPLE_NAME.fullmatch(path.stem) and 0 < size <= MAX_SAMPLE_BYTES:
                samples.append(
                    {"name": path.stem, "lang": path.stem[:2], "seconds": round(size / 8000, 1)}
                )
    return JSONResponse({"samples": samples}, headers=NO_STORE)


@router.get("/samples/{name}.ulaw")
async def get_sample(name: str, request: Request) -> FileResponse:
    path = _samples_dir(request) / f"{name}.ulaw"
    if not SAMPLE_NAME.fullmatch(name) or not path.is_file():
        raise HTTPException(status_code=404, detail="sample not found")
    if path.stat().st_size > MAX_SAMPLE_BYTES:
        raise HTTPException(status_code=413, detail="sample too large")
    return FileResponse(path, media_type="audio/basic", headers=NO_STORE)


@router.post("/calls")
async def create_dev_call(body: DevCallRequest, request: Request) -> JSONResponse:
    services = get_services(request)
    if not services.voice_rate_limiter.allow():
        return JSONResponse({"error": "rate_limited"}, status_code=429)
    lang: Lang = body.lang or services.hub.lang(services.settings.DEFAULT_LANG)
    call_id = "CA" + secrets.token_hex(16)
    result = admit_call(services, call_id, body.caller, lang)
    if result.outcome is not AdmitOutcome.ADMITTED or result.token is None:
        return JSONResponse(
            {
                "error": "protection_unavailable",
                "reason": result.outcome.value,
                "message": PROTECTION_UNAVAILABLE[lang],
            },
            status_code=503,
        )
    return JSONResponse(
        {
            "callId": call_id,
            "token": result.token,
            "lang": lang,
            "provider": services.provider.name,
            "streamPath": f"/{services.provider.name}/stream",
            "notice": PROTECTION_NOTICE[lang],
            "trusted": services.hub.is_whitelisted(body.caller),
        },
        headers=NO_STORE,
    )


def mount_dev_tools(app: FastAPI) -> None:
    app.include_router(router)
    app.mount("/dev/static", StaticFiles(directory=STATIC_DIR), name="dev-static")
