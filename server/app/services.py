"""Container for the long-lived objects shared by routes (stored on `app.state.services`)."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request
from starlette.requests import HTTPConnection

from app.config import Settings
from app.relay.hub import AppHub
from app.risk.engine import RiskEngine
from app.session import CallSession
from app.stt.base import STTBackend
from app.telephony.admission import CallAdmission, SlidingWindowRateLimiter
from app.telephony.guard import GuardedCallActions
from app.telephony.provider import TelephonyProvider


@dataclass
class Services:
    settings: Settings
    provider: TelephonyProvider
    hub: AppHub
    stt: STTBackend
    engine: RiskEngine
    actions: GuardedCallActions
    admission: CallAdmission
    voice_rate_limiter: SlidingWindowRateLimiter
    decision_backend_name: str | None = None  # active decision backend, None = rules only
    sessions: dict[str, CallSession] = field(default_factory=dict)


def get_services(conn: HTTPConnection | Request) -> Services:
    return conn.app.state.services
