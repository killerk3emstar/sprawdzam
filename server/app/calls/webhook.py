"""`POST /<provider>/voice`: incoming-call webhook (Twilio: `/twilio/voice`).

Order of checks: content type -> body size -> provider signature -> rate limit -> call
fields -> senior app online -> concurrency slot. On success the markup plays the protection
notice and connects the call audio to our media stream WebSocket. Without an app online or
a free slot the caller hears "protection temporarily unavailable" and the call ends.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qsl

from fastapi import Request
from fastapi.responses import PlainTextResponse, Response
from starlette.datastructures import FormData

from app.calls.intake import AdmitOutcome, admit_call
from app.config import Lang
from app.logging_setup import log_event
from app.services import get_services
from app.telephony.provider import InvalidWebhook, WebhookForbidden

logger = logging.getLogger(__name__)

MAX_WEBHOOK_BYTES = 16 * 1024
MAX_FORM_FIELDS = 200


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


async def incoming_call(request: Request) -> Response:
    services = get_services(request)
    settings = services.settings
    provider = services.provider

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

    auth = provider.verify_webhook(request.url.path, request.url.query, form, request.headers)
    if not auth.accepted:
        log_event(
            logger, logging.WARNING, "webhook_rejected", reason=auth.value, path=request.url.path
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

    try:
        call = provider.parse_incoming_call(form)
    except WebhookForbidden as exc:
        log_event(logger, logging.WARNING, "webhook_rejected", reason=str(exc))
        return PlainTextResponse("forbidden", status_code=403)
    except InvalidWebhook as exc:
        return PlainTextResponse(str(exc), status_code=400)

    # TODO: per-senior language from the family panel (look up by the forwarded number).
    lang: Lang = settings.DEFAULT_LANG
    result = admit_call(services, call.call_id, call.caller, lang)
    if result.outcome is not AdmitOutcome.ADMITTED or result.token is None:
        markup = provider.unavailable_markup(lang)
    else:
        stream_url = settings.ws_url(f"/{provider.name}/stream")
        markup = provider.connect_markup(stream_url, lang, call.call_id, result.token)
    return Response(content=markup, media_type=provider.markup_media_type)
