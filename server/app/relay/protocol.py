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
MAX_CONTROL_TEXT_CHARS = 128 * 1024  # settings with a whitelist of up to MAX_WHITELIST numbers
MAX_WHITELIST = 2000

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


def incoming_call(
    call_id: str, token: str, caller: str, lang: Lang, trusted: bool = False
) -> dict[str, object]:
    return {
        "type": "incoming_call",
        "callId": call_id,
        "token": token,
        "caller": caller,
        "lang": lang,
        "trusted": trusted,
    }


def settings_ack(
    accepted: bool, whitelist: int = 0, ignored: int = 0, error: str | None = None
) -> dict[str, object]:
    message: dict[str, object] = {"type": "settings_ack", "accepted": accepted}
    if accepted:
        message.update(whitelist=whitelist, ignored=ignored)
    else:
        message["error"] = error or "invalid_settings"
    return message


def risk_event(assessment: RiskAssessment) -> dict[str, object]:
    return {
        "type": "risk",
        "score": int(assessment.smoothed_score),
        "level": _LEVELS[assessment.level],
        "scamType": assessment.scam_type.value,
        "reasons": [name for name, on in assessment.categories.items() if on],
    }


def verify_password(timeout_seconds: int) -> dict[str, object]:
    return {"type": "verify_password", "timeoutSeconds": int(timeout_seconds)}


def confirm_block(seconds: int) -> dict[str, object]:
    """No family password configured: the call is blocked after `seconds`."""
    return {"type": "confirm_block", "seconds": int(seconds)}


def call_ended(reason: EndReason) -> dict[str, object]:
    return {"type": "call_ended", "reason": reason.value}


def alert_trusted(
    call_id: str, scam_type: str, reasons: list[str], lang: Lang, text: str
) -> dict[str, object]:
    """Control channel: ask the senior's phone to text the trusted person."""
    return {
        "type": "alert_trusted",
        "callId": call_id,
        "scamType": scam_type,
        "reasons": list(reasons),
        "lang": lang,
        "text": text,
    }


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


class TrustedPerson(_AppMsg):
    name: Annotated[str, StringConstraints(max_length=80)] = ""
    number: Annotated[str, StringConstraints(max_length=32)]


class SettingsMessage(_AppMsg):
    """Senior's settings, sent on the control channel after connecting and on every change.
    Each message replaces the previous settings completely."""

    type: Literal["settings"]
    lang: Lang
    trustedPerson: TrustedPerson | None = None
    whitelist: list[Annotated[str, StringConstraints(max_length=32)]] = Field(
        default_factory=list, max_length=MAX_WHITELIST
    )


class AlertTrustedResult(_AppMsg):
    """Control channel: the app's answer to `alert_trusted`."""

    type: Literal["alert_trusted_result"]
    callId: Annotated[str, StringConstraints(pattern=CALL_ID_PATTERN)]
    sent: bool
    error: Annotated[str, StringConstraints(max_length=40)] | None = None


AppMessage = Annotated[
    Ping | Accept | Hangup | Dtmf | SettingsMessage | AlertTrustedResult,
    Field(discriminator="type"),
]
_adapter: TypeAdapter[AppMessage] = TypeAdapter(AppMessage)
_KNOWN = {"ping", "accept", "hangup", "dtmf", "settings", "alert_trusted_result"}


class BadAppMessage(ValueError):
    pass


def parse_app_message(text: str, max_chars: int = MAX_APP_TEXT_CHARS) -> AppMessage | None:
    """Parse one JSON text frame. None for unknown types (ignored by protocol).
    Raises BadAppMessage for invalid JSON or invalid fields."""
    if len(text) > max_chars:
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
