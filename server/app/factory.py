"""Application factory. Tests build the app with fakes; `app.main` builds it from env."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.calls.stream import media_stream
from app.calls.webhook import incoming_call
from app.config import Settings, get_settings
from app.health import router as health_router
from app.logging_setup import configure_logging, log_event
from app.relay.hub import AppHub
from app.relay.routes import router as relay_router
from app.risk.decision import DecisionBackend
from app.risk.engine import RiskEngine
from app.services import Services
from app.stt.base import NoopSTT, STTBackend
from app.telephony.actions import CallActions
from app.telephony.admission import CallAdmission, SlidingWindowRateLimiter
from app.telephony.guard import DailyCounterStore, GuardConfig, GuardedCallActions
from app.telephony.provider import TelephonyProvider
from app.twilio.provider import TwilioProvider

logger = logging.getLogger(__name__)


def build_decision_backend(settings: Settings) -> DecisionBackend | None:
    if settings.DECISION_BACKEND == "rules":
        return None
    # The basal-1 / Clef-Flash HTTP clients are not implemented yet.
    log_event(
        logger,
        logging.WARNING,
        "decision_backend_not_implemented",
        configured=settings.DECISION_BACKEND,
        active="rules",
    )
    return None


def build_stt(settings: Settings) -> STTBackend:
    if settings.WHISPER_URL:
        log_event(logger, logging.WARNING, "stt_backend_not_implemented", active="noop")
    return NoopSTT()


def build_call_actions(
    settings: Settings,
    inner: CallActions,
    counters: DailyCounterStore | None = None,
) -> GuardedCallActions:
    """Every CallActions implementation (the provider's REST API) is wrapped in the
    cost/safety guard."""
    config = GuardConfig(
        dry_run=settings.TELEPHONY_DRY_RUN,
        allowlist=settings.outbound_allowlist,
        own_number=settings.TWILIO_NUMBER,
        max_calls_per_day=settings.MAX_OUTBOUND_CALLS_PER_DAY,
        max_sms_per_day=settings.MAX_SMS_PER_DAY,
    )
    return GuardedCallActions(inner, config, counters or DailyCounterStore(settings.DATA_DIR))


def _startup_warnings(settings: Settings) -> None:
    if not settings.twilio_auth_token:
        if settings.ALLOW_UNSIGNED_WEBHOOKS:
            log_event(
                logger,
                logging.WARNING,
                "unsigned_webhooks_allowed",
                note="development only, never in production",
            )
        else:
            log_event(
                logger,
                logging.WARNING,
                "twilio_auth_token_missing",
                note="Twilio webhooks will be refused with 403",
            )
    if not settings.PUBLIC_BASE_URL.startswith("https://"):
        log_event(
            logger,
            logging.WARNING,
            "public_base_url_not_https",
            note="Twilio requires https/wss in production",
        )
    if not settings.TELEPHONY_DRY_RUN:
        log_event(
            logger,
            logging.WARNING,
            "telephony_live_mode",
            note="outbound calls and SMS can spend money",
        )
    if not settings.APP_DEVICE_TOKEN.get_secret_value():
        log_event(
            logger,
            logging.WARNING,
            "app_device_token_missing",
            note="the senior app cannot connect, so every call hears 'protection unavailable'",
        )
    if settings.DEV_TOOLS:
        log_event(
            logger,
            logging.WARNING,
            "dev_tools_enabled",
            note="/dev/caller and /dev/senior are served; never enable in production",
        )
    trusted = settings.TRUSTED_PERSON_NUMBER
    if trusted and trusted not in settings.outbound_allowlist:
        log_event(
            logger,
            logging.WARNING,
            "trusted_person_not_allowlisted",
            note="alerts to the trusted person will be refused",
        )


def create_app(
    settings: Settings | None = None,
    *,
    provider: TelephonyProvider | None = None,
    stt: STTBackend | None = None,
    decision_backend: DecisionBackend | None = None,
    inner_actions: CallActions | None = None,
    counters: DailyCounterStore | None = None,
) -> FastAPI:
    """`inner_actions` replaces the provider's REST actions (tests); it is still guarded."""
    settings = settings or get_settings()
    provider = provider or TwilioProvider(settings)
    decision = decision_backend or build_decision_backend(settings)
    services = Services(
        settings=settings,
        provider=provider,
        hub=AppHub(settings.APP_DEVICE_TOKEN.get_secret_value()),
        stt=stt or build_stt(settings),
        engine=RiskEngine(
            warn_threshold=settings.RISK_WARN,
            hangup_threshold=settings.RISK_HANGUP,
            decision_backend=decision,
            decision_timeout_seconds=settings.DECISION_TIMEOUT_SECONDS,
        ),
        actions=build_call_actions(settings, inner_actions or provider, counters),
        admission=CallAdmission(settings.MAX_CONCURRENT_CALLS),
        voice_rate_limiter=SlidingWindowRateLimiter(settings.MAX_INCOMING_CALLS_PER_MINUTE),
        decision_backend_name=getattr(decision, "name", None) if decision else None,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.LOG_LEVEL)
        _startup_warnings(settings)
        yield
        await services.hub.shutdown()

    app = FastAPI(
        title="Sprawdzam / Second Ear backend",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.services = services
    app.include_router(health_router)
    # Provider routes carry the provider name: POST /twilio/voice, WS /twilio/stream.
    app.add_api_route(f"/{provider.name}/voice", incoming_call, methods=["POST"])
    app.add_api_websocket_route(f"/{provider.name}/stream", media_stream)
    app.include_router(relay_router)
    if settings.DEV_TOOLS:
        from app.dev.routes import mount_dev_tools

        mount_dev_tools(app)
    return app
