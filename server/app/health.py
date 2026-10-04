"""`GET /health`: liveness plus which backends and limits are configured (no secrets)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__
from app.services import get_services

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    services = get_services(request)
    settings = services.settings
    token_set = bool(settings.twilio_auth_token)
    if token_set:
        signature_mode = "enforced"
    elif settings.ALLOW_UNSIGNED_WEBHOOKS:
        signature_mode = "disabled_dev"
    else:
        signature_mode = "refusing_webhooks"
    return {
        "status": "ok",
        "version": __version__,
        "default_lang": settings.DEFAULT_LANG,
        "protection": "model+rules" if services.decision_backend_name else "rules_only",
        "provider": services.provider.name,
        "app": {
            "device_token_configured": services.hub.device_token_configured,
            "connected": services.hub.online,
            "control_connections": services.hub.control_count,
            "protocol": "v0",
        },
        "dev_tools": settings.DEV_TOOLS,
        "twilio": {
            "account_sid_configured": bool(settings.TWILIO_ACCOUNT_SID),
            "auth_token_configured": token_set,
            "number_configured": bool(settings.TWILIO_NUMBER),
            "signature_validation": signature_mode,
            "public_base_url_https": settings.PUBLIC_BASE_URL.startswith("https://"),
        },
        "stt": {
            "backend": getattr(services.stt, "name", type(services.stt).__name__),
            "whisper_url_configured": bool(settings.WHISPER_URL),
        },
        "decision": {
            "configured": settings.DECISION_BACKEND,
            "active": services.decision_backend_name or "rules",
            "basal_url_configured": bool(settings.BASAL_URL),
            "clef_url_configured": bool(settings.CLEF_URL),
            "timeout_seconds": settings.DECISION_TIMEOUT_SECONDS,
        },
        "models": services.models.as_dict(),
        "voice_prompts": services.prompts.status(),
        "risk": {
            "warn": settings.RISK_WARN,
            "hangup": settings.RISK_HANGUP,
            "secrecy_hangup_min": settings.SECRECY_HANGUP_MIN,
        },
        "limits": {
            **services.actions.status(),
            "trusted_person_configured": bool(settings.TRUSTED_PERSON_NUMBER),
            "max_concurrent_calls": settings.MAX_CONCURRENT_CALLS,
            "max_call_seconds": settings.MAX_CALL_SECONDS,
            "max_incoming_calls_per_minute": settings.MAX_INCOMING_CALLS_PER_MINUTE,
        },
        "calls": {
            "active": services.admission.active_count,
            "pending": services.admission.pending_count,
        },
    }
