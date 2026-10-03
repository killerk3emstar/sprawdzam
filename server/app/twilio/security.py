"""Twilio webhook signature validation (`X-Twilio-Signature`)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum

from twilio.request_validator import RequestValidator

from app.config import Settings
from app.logging_setup import log_event

logger = logging.getLogger(__name__)


class SignatureCheck(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING = "missing"
    NOT_CONFIGURED = "not_configured"  # no auth token and unsigned webhooks not allowed
    SKIPPED_DEV = "skipped_dev"  # no auth token, ALLOW_UNSIGNED_WEBHOOKS=true


def check_signature(
    settings: Settings,
    path: str,
    query: str,
    params: Mapping[str, object] | None,
    signature: str | None,
) -> SignatureCheck:
    """Validate a Twilio request.

    The URL is rebuilt from PUBLIC_BASE_URL because the app runs behind a tunnel or reverse
    proxy, so the Host/scheme the app sees differ from what Twilio signed.
    """
    token = settings.twilio_auth_token
    if not token:
        if settings.ALLOW_UNSIGNED_WEBHOOKS:
            log_event(
                logger,
                logging.WARNING,
                "twilio_signature_skipped",
                reason="TWILIO_AUTH_TOKEN empty and ALLOW_UNSIGNED_WEBHOOKS=true",
                path=path,
            )
            return SignatureCheck.SKIPPED_DEV
        return SignatureCheck.NOT_CONFIGURED
    if not signature:
        return SignatureCheck.MISSING
    url = settings.public_url(path, query)
    valid = RequestValidator(token).validate(url, params or {}, signature)
    return SignatureCheck.VALID if valid else SignatureCheck.INVALID


def is_accepted(check: SignatureCheck) -> bool:
    return check in (SignatureCheck.VALID, SignatureCheck.SKIPPED_DEV)
