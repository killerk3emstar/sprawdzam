"""`POST /twilio/voice`: Twilio incoming-call webhook.

Order of checks: content type -> body size -> X-Twilio-Signature -> rate limit -> CallSid /
AccountSid -> concurrency slot. On success the TwiML plays the protection notice and connects
the call audio to our Media Stream WebSocket.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response
from starlette.datastructures import FormData
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.config import Lang, Settings
from app.logging_setup import log_event
from app.services import get_services
from app.twilio.prompts import PROTECTION_NOTICE, PROTECTION_UNAVAILABLE, VOICES
from app.twilio.security import check_signature, is_accepted

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_WEBHOOK_BYTES = 16 * 1024
MAX_FORM_FIELDS = 200
CALL_SID_RE = re.compile(r"^CA[0-9a-f]{32}$")
ACCOUNT_SID_RE = re.compile(r"^AC[0-9a-f]{32}$")


class _BodyTooLarge(Exception):
    pass


async def _read_limited(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > limit):
        raise _BodyTooLarge
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise _BodyTooLarge
    return bytes(body)


def connect_twiml(settings: Settings, lang: Lang, call_sid: str, token: str) -> str:
    voice = VOICES[lang]
    response = VoiceResponse()
    response.say(PROTECTION_NOTICE[lang], voice=voice.voice, language=voice.language)
    connect = Connect()
    stream = connect.stream(url=settings.stream_url)
    stream.parameter(name="token", value=token)
    stream.parameter(name="lang", value=lang)
    stream.parameter(name="callId", value=call_sid)
    response.append(connect)
    return str(response)


def unavailable_twiml(lang: Lang) -> str:
    voice = VOICES[lang]
    response = VoiceResponse()
    response.say(PROTECTION_UNAVAILABLE[lang], voice=voice.voice, language=voice.language)
    response.hangup()
    return str(response)


def _xml(content: str) -> Response:
    return Response(content=content, media_type="application/xml")


@router.post("/twilio/voice")
async def incoming_call(request: Request) -> Response:
    services = get_services(request)
    settings = services.settings

    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/x-www-form-urlencoded"):
        return PlainTextResponse("unsupported media type", status_code=415)
    try:
        body = await _read_limited(request, MAX_WEBHOOK_BYTES)
        pairs = parse_qsl(
            body.decode("utf-8"),
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=MAX_FORM_FIELDS,
        )
    except _BodyTooLarge:
        return PlainTextResponse("payload too large", status_code=413)
    except (UnicodeDecodeError, ValueError):
        return PlainTextResponse("malformed form body", status_code=400)
    form = FormData(pairs)

    check = check_signature(
        settings,
        request.url.path,
        request.url.query,
        form,
        request.headers.get("x-twilio-signature"),
    )
    if not is_accepted(check):
        log_event(
            logger,
            logging.WARNING,
            "twilio_webhook_rejected",
            reason=check.value,
            path=request.url.path,
        )
        return PlainTextResponse("forbidden", status_code=403)

    if not services.voice_rate_limiter.allow():
        log_event(
            logger,
            logging.WARNING,
            "incoming_call_rate_limited",
            limit_per_minute=settings.MAX_INCOMING_CALLS_PER_MINUTE,
        )
        return PlainTextResponse("too many calls", status_code=429)

    call_sid = str(form.get("CallSid") or "")
    if not CALL_SID_RE.fullmatch(call_sid):
        return PlainTextResponse("missing or invalid CallSid", status_code=400)
    account_sid = str(form.get("AccountSid") or "")
    if account_sid and not ACCOUNT_SID_RE.fullmatch(account_sid):
        return PlainTextResponse("invalid AccountSid", status_code=400)
    if settings.TWILIO_ACCOUNT_SID and account_sid != settings.TWILIO_ACCOUNT_SID:
        log_event(logger, logging.WARNING, "twilio_webhook_rejected", reason="account_mismatch")
        return PlainTextResponse("forbidden", status_code=403)

    # TODO: per-senior language from the family panel (look up by the forwarded number).
    lang: Lang = settings.DEFAULT_LANG
    token = services.admission.admit(call_sid)
    if token is None:
        log_event(
            logger,
            logging.WARNING,
            "incoming_call_rejected_capacity",
            call_id=call_sid,
            max_concurrent=settings.MAX_CONCURRENT_CALLS,
        )
        return _xml(unavailable_twiml(lang))

    log_event(
        logger,
        logging.INFO,
        "incoming_call_accepted",
        call_id=call_sid,
        lang=lang,
        signature=check.value,
    )
    return _xml(connect_twiml(settings, lang, call_sid, token))
