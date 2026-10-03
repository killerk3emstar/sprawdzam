# Sprawdzam / Second Ear: backend

FastAPI service that answers forwarded calls through Twilio, streams the caller's audio over a
WebSocket, transcribes it and scores the scam risk in real time.

```
Twilio ── POST /twilio/voice ──► signature check, rate limit, call slot ──► TwiML:
                                  <Say> protection notice + <Connect><Stream wss://…/twilio/stream>
Twilio ══ WS /twilio/stream ══► μ-law 8 kHz → PCM → 16 kHz → 3 s windows → STTBackend
                                  → RiskEngine (DecisionBackend + keyword rules → smoothing)
                                  → IncidentResponder → GuardedCallActions → CallActions
```

Status of this iteration: everything external sits behind an interface. Speech-to-text is a
no-op (`NoopSTT`), the decision model is not wired in (rules only) and `CallActions` only logs.
The whisper.cpp, basal-1 and Twilio REST clients come next.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.12 is pinned in `.python-version`; uv downloads it)

## Install, run, test

```bash
cd server
uv sync                                    # creates .venv with locked dependencies
uv run uvicorn app.main:app --reload       # http://127.0.0.1:8000/health
uv run pytest                              # full test suite, no network access needed
uv run ruff check . && uv run ruff format --check .
```

Configuration comes from environment variables or a `.env` file (the repository root `.env`
first, then an optional `server/.env`). Copy `../.env.example` to `../.env`. Without
`TWILIO_AUTH_TOKEN` all Twilio webhooks are refused (403); for local experiments only, set
`ALLOW_UNSIGNED_WEBHOOKS=true`.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness, configured backends and limits. Never returns secrets or phone numbers. |
| `POST /twilio/voice` | Twilio incoming-call webhook. Returns TwiML. |
| `WS /twilio/stream` | Twilio bidirectional Media Stream for one call. |

## Layout

```
app/
  config.py            settings (names match ../.env.example)
  factory.py, main.py  app factory (tests inject fakes) and ASGI entry point
  health.py
  audio/               G.711 μ-law codec (numpy lookup tables), soxr resampling
  stt/                 STTBackend protocol + NoopSTT
  risk/                rules.py (PL+EN), smoothing.py, decision.py (model interface), engine.py
  session.py           per-call pipeline (RAM only), transcript.py (rolling 60 s window)
  twilio/              voice webhook, media stream, message validation, signature check, prompts
  telephony/           CallActions, cost/safety guard, admission control, incident responder
tests/                 pytest suite (fakes for STT, decision model and Twilio actions)
```

## Security and privacy

- `X-Twilio-Signature` is validated with Twilio's `RequestValidator` against
  `PUBLIC_BASE_URL + path` (the app runs behind a tunnel or proxy, so the Host header is not
  trusted). Invalid or missing signature: 403. Request body limited to 16 KiB, form only.
- The media stream must present a one-time token (issued by `/twilio/voice`, bound to the
  CallSid, valid 2 minutes) in its `start` message, otherwise it is closed with code 1008.
  The `X-Twilio-Signature` header on the WebSocket handshake is only logged until we have
  checked it against a real Twilio account.
- Media messages are validated with pydantic; malformed ones are logged (error type and field
  only, never payloads) and skipped. More than 50 malformed messages close the stream.
- Audio and transcripts live only in the per-call session object in RAM and are cleared when
  the stream stops. Logs contain call ids, scores, categories and error types; never transcript
  text, audio, DTMF digits or full phone numbers (numbers are masked, e.g. `+48*******01`).
- Secrets are `SecretStr` and never logged; settings validation errors hide input values.

## Risk engine

- `rules.py`: Polish and English keyword/phrase rules on normalised text (lowercase, no
  diacritics, no punctuation; Polish stems cover inflection). Each rule belongs to a category
  (money, secrecy, authority, urgency) as weak or strong, or adds "story" context points
  (accident, bail, account at risk…). A category counts once. Pair bonuses make combinations
  score far higher than single words: "pieniądze" alone ≈ 12, authority + money + secrecy ≥ 80.
- `smoothing.py`: warning when the moving average of the last 2 readings ≥ `RISK_WARN`;
  hang-up only when the last 2 readings are both ≥ `RISK_HANGUP`. One spike never hangs up.
- `engine.py`: the decision model is optional. Timeout (`DECISION_TIMEOUT_SECONDS`), HTTP
  error, malformed or out-of-range answer → structured warning `decision_fallback_to_rules`
  and rules only. Combined score = max(model, rules). Actions only escalate:
  none → warn → verify_family_password_then_hangup.

## Telephony cost and safety guard

Anything that can spend Twilio money goes through `GuardedCallActions`
(`app/telephony/guard.py`); `build_call_actions` always wraps the real implementation.

| Guard | Setting (default) | Behaviour |
| --- | --- | --- |
| Dry run | `TELEPHONY_DRY_RUN=true` | Outbound calls, SMS and REST hang-ups are logged as `telephony_would_<action>` and not executed. Real actions only when explicitly `false`. |
| Allowlist | `OUTBOUND_ALLOWLIST=` (empty) | Comma-separated E.164 numbers. Any other destination, a malformed number or our own `TWILIO_NUMBER` (call loop) is refused and logged. |
| Daily caps | `MAX_OUTBOUND_CALLS_PER_DAY=10`, `MAX_SMS_PER_DAY=20` | Counted per UTC day in `DATA_DIR/telephony_counters.json` (date and counts only). Reserved before the action runs; survives restarts. Unreadable counter file → outbound refused (fail closed for spending). |
| Per-incident dedupe | always on | At most one hang-up, one trusted-person call and one SMS per incoming call, however many high readings arrive. |
| Concurrency | `MAX_CONCURRENT_CALLS=2` | Pending + active calls. Extra `/twilio/voice` requests get TwiML `<Say>` "protection temporarily unavailable" (PL/EN) + `<Hangup/>`; streams without a slot/token are refused. |
| Call duration | `MAX_CALL_SECONDS=600` | The stream closes itself after the limit. Closing the WebSocket ends `<Connect>`; there is no further TwiML verb, so Twilio hangs up the call. |
| Rate limit | `MAX_INCOMING_CALLS_PER_MINUTE=10` | In-memory sliding window on signed `/twilio/voice` requests → HTTP 429 (Twilio then uses the number's fallback URL, if configured, or ends the call). |

Order of checks for outbound actions: number format → own number → allowlist → dedupe →
dry run → daily cap → execute. Dry-run actions do not count against the caps. The guard and
the admission state are per process: run a single uvicorn worker.

`TRUSTED_PERSON_NUMBER` (E.164) is the person alerted on high risk; it must also be on the
allowlist. Until the family panel exists this is the only trusted person.

## Fail-open behaviour

- STT failure or timeout: logged (`stt_failed`), the call continues, the session is marked
  degraded.
- Decision model failure: rules only.
- A failing action never stops the call or the other incident steps.
- Backend down entirely: configure a Twilio fallback URL (e.g. a TwiML Bin that dials the
  senior directly) so calls still go through.

## Not done yet

- whisper.cpp HTTP client, basal-1 / Clef-Flash clients, Silero VAD (an RMS gate skips silent
  windows for now)
- Twilio REST `CallActions` (hang-up, call, SMS) and the in-call voice warning (`send_audio`
  in `app/twilio/stream.py` is ready for it)
- Family-password check before hang-up, `/app/{callId}` WebSocket relay to the senior's app,
  per-senior language and trusted contacts from the family panel
- Dockerfile / docker compose
