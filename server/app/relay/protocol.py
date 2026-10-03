"""App protocol v0 message builders, validation and constants (docs/APP_PROTOCOL.md)."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError

from app.config import Lang
from app.risk.models import Action

if TYPE_CHECKING:
    from app.risk.engine import RiskAssessment

PROTOCOL_VERSION = "v0"
CALL_TOKEN_TTL_SECONDS = 300.0
CONTROL_IDLE_TIMEOUT_SECONDS = 45.0
MAX_APP_AUDIO_FRAME_BYTES = 6400  # 200 ms of PCM16 16 kHz
MAX_APP_TEXT_CHARS = 4096

CLOSE_NORMAL = 1000
CLOSE_POLICY = 1008
CLOSE_IDLE = 4000

CALL_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class EndReason(StrEnum):
    CALLER_HANGUP = "caller_hangup"
    SENIOR_HANGUP = "senior_hangup"
    SCAM_BLOCKED = "scam_blocked"
    TIMEOUT = "timeout"
    ERROR = "error"


_LEVELS = {Action.NONE: "none", Action.WARN: "warn", Action.VERIFY_THEN_HANGUP: "high"}


# ---------------------------------------------------------------------- backend -> app
def protection_status(available: bool) -> dict[str, object]:
    return {"type": "protection_status", "available": available}


def pong() -> dict[str, object]:
    return {"type": "pong"}


def incoming_call(call_id: str, token: str, caller: str, lang: Lang) -> dict[str, object]:
    return {
        "type": "incoming_call",
        "callId": call_id,
        "token": token,
        "caller": caller,
        "lang": lang,
    }


def risk_event(assessment: RiskAssessment) -> dict[str, object]:
    return {
        "type": "risk",
        "score": int(assessment.smoothed_score),
        "level": _LEVELS[assessment.level],
        "scamType": assessment.scam_type.value,
        "reasons": [name for name, on in assessment.categories.items() if on],
    }


def verify_password() -> dict[str, object]:
    return {"type": "verify_password"}


def call_ended(reason: EndReason) -> dict[str, object]:
    return {"type": "call_ended", "reason": reason.value}


# ---------------------------------------------------------------------- app -> backend
class _AppMsg(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class Ping(_AppMsg):
    type: Literal["ping"]


class Accept(_AppMsg):
    type: Literal["accept"]


class Hangup(_AppMsg):
    type: Literal["hangup"]


class Dtmf(_AppMsg):
    type: Literal["dtmf"]
    digits: Annotated[str, StringConstraints(pattern=r"^[0-9*#]{1,32}$")]


AppMessage = Annotated[Ping | Accept | Hangup | Dtmf, Field(discriminator="type")]
_adapter: TypeAdapter[AppMessage] = TypeAdapter(AppMessage)
_KNOWN = {"ping", "accept", "hangup", "dtmf"}


class BadAppMessage(ValueError):
    pass


def parse_app_message(text: str) -> AppMessage | None:
    """Parse one JSON text frame. None for unknown types (ignored by protocol).
    Raises BadAppMessage for invalid JSON or invalid fields."""
    if len(text) > MAX_APP_TEXT_CHARS:
        raise BadAppMessage("message_too_large")
    try:
        data = json.loads(text)
    except ValueError:
        raise BadAppMessage("invalid_json") from None
    if not isinstance(data, dict):
        raise BadAppMessage("not_an_object")
    if data.get("type") not in _KNOWN:
        return None
    try:
        return _adapter.validate_python(data)
    except ValidationError:
        raise BadAppMessage("schema") from None
