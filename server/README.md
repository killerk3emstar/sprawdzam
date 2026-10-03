# Sprawdzam / Second Ear: backend

FastAPI service that answers forwarded calls through a telephony provider (Twilio for now),
relays the call audio to the senior's app, transcribes the caller and scores the scam risk in
real time.

```
provider ── POST /twilio/voice ──► signature, rate limit, app online?, call slot ──► TwiML:
                                    <Say> protection notice + <Connect><Stream wss://…/twilio/stream>
provider ══ WS /twilio/stream ══► μ-law 8 kHz → PCM 16 kHz ─┬─► 3 s windows → STTBackend
                                                             │     → RiskEngine (model + rules)
                                                             │     → IncidentResponder
                                                             └─► CallBridge ══ WS /app/call/{id} ══► senior app
senior app ══ WS /app/control (incoming_call, protection status) ══ AppHub
```

Status: everything external sits behind an interface. Speech-to-text is a no-op (`NoopSTT`)
and the decision model is not wired in (rules only); the whisper.cpp and basal-1 clients come
next. Twilio REST actions exist but run in dry-run mode by default.

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
`ALLOW_UNSIGNED_WEBHOOKS=true`. Without `APP_DEVICE_TOKEN` the senior app cannot connect, so
every call hears "protection temporarily unavailable".

## 5-minute manual test in the browser (no phone, no Twilio account)

```bash
cd server
DEV_TOOLS=true APP_DEVICE_TOKEN=dev-token-change-me-123 uv run uvicorn app.main:app --port 8000
```

1. Open <http://localhost:8000/dev/senior>, paste `dev-token-change-me-123` as the device
   token and click **Turn protection on**. "Protection: on" means the control channel is open.
2. Open <http://localhost:8000/dev/caller> in a second tab and click **Call**. The browser asks
   for the microphone. The senior tab shows the incoming call (masked number) and the caller
   tab hears the 425 Hz ringback tone.
3. Click **Accept** in the senior tab (it asks for the microphone too). The ringback stops.
4. Speak into the microphone: the caller tab's voice comes out of the senior tab and the
   other way round. Use headphones, otherwise two tabs on one computer feed back.
5. Click **Hang up** in either tab; the other side shows the call as ended.

With `NoopSTT` there is no transcript, so the risk bar stays at 0. The browser needs a secure
context for the microphone: `http://localhost` works, a LAN IP needs HTTPS (e.g. a tunnel).
Not accepting within 30 s ends the call (`timeout`). The caller keypad sends DTMF, which is
used for the family-password check (`FAMILY_PASSWORD`). `/dev/caller` speaks the Twilio media
stream format over the same WebSocket the real provider uses.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness, provider, app connection, backends and limits. No secrets or numbers. |
| `POST /twilio/voice` | Provider incoming-call webhook. Returns TwiML. |
| `WS /twilio/stream` | Provider bidirectional media stream for one call. |
| `WS /app/control?device_token=…` | Senior app control channel (protocol v0). |
| `WS /app/call/{callId}?token=…` | Senior app call channel: audio + risk events (protocol v0). |
| `GET /dev/caller`, `GET /dev/senior`, `POST /dev/calls` | Browser test tools, only with `DEV_TOOLS=true`. |

The app protocol is specified in [`docs/APP_PROTOCOL.md`](../docs/APP_PROTOCOL.md).

## Layout

```
app/
  config.py            settings (names match ../.env.example)
  factory.py, main.py  app factory (tests inject fakes) and ASGI entry point
  health.py, prompts.py
  audio/               G.711 μ-law codec (numpy tables), soxr resampling, PCM16/μ-law framing
  stt/                 STTBackend protocol + NoopSTT
  risk/                rules.py (PL+EN), smoothing.py, decision.py (model interface), engine.py
  session.py           per-call STT pipeline (RAM only), transcript.py (rolling 60 s window)
  calls/               provider-neutral webhook, media stream handler, CallBridge, tones
  relay/               app protocol v0: AppHub, control/call WebSockets, message schema
  telephony/           TelephonyProvider interface, cost/safety guard, admission, responder
  twilio/              Twilio provider: TwiML, signature, stream message models, REST client
  dev/                 DEV_TOOLS pages (plain HTML + vanilla JS, no build step)
tests/                 pytest suite (fakes for STT, decision model, provider REST, app)
```

## Telephony provider adapter

All provider-specific code is behind `TelephonyProvider` (`app/telephony/provider.py`):
webhook authentication and parsing, call-control markup, media-stream message parsing and
encoding (into provider-neutral `Stream*` events), and the REST actions (hang-up, call, SMS).
`TwilioProvider` (`app/twilio/provider.py`) is the only implementation. Routes use the
provider name as prefix (`/twilio/voice`, `/twilio/stream`).

What a SignalWire adapter (`app/signalwire/provider.py`, `name = "signalwire"`) would change.
Based on SignalWire's cXML `<Stream>` and webhook-security docs; verify against a real
account before relying on it:

- **Webhook auth:** HMAC signature in `X-SignalWire-Signature` (legacy `X-Twilio-Signature`
  also sent), computed with the Signing Key from the dashboard over the full URL and body.
  Implement `verify_webhook` with that key.
- **Stream auth:** SignalWire supports an `authBearerToken` attribute on `<Stream>` (sent as
  `Authorization` on the WebSocket handshake). Use it for `verify_stream_handshake`; keep the
  one-time `<Parameter name="token">` check as is.
- **IDs:** call and stream IDs are not Twilio `CA…`/`MZ…` SIDs. Replace the SID regexes in
  `parse_incoming_call` and the message models; the app protocol `callId` pattern already
  accepts UUIDs.
- **Markup:** cXML mirrors TwiML (`<Say>`, `<Connect><Stream>`, `<Parameter>`, `<Hangup>`);
  only the `<Say>` voice names differ. `<Connect><Stream>` is bidirectional; `codec` defaults
  to `PCMU@8000h` (`L16@16000h` would remove our resampling later).
- **Stream messages:** same event names and fields (`connected`, `start` with `streamSid`,
  `callSid`, `customParameters`, `mediaFormat`; `media`, `dtmf`, `mark`, `stop`), and the
  server can send `media`, `mark`, `clear`. Mostly a copy of the Twilio models.
- **REST:** Compatibility API at `https://<space>.signalwire.com/api/laml/2010-04-01/Accounts/<project>/…`
  with project ID + API token (Basic auth): a copy of `TwilioRest` with another base URL and
  credentials. New settings: space, project ID, API token, signing key, own number.
- **Settings:** the guard's "own number" is read from `TWILIO_NUMBER` in `app/factory.py`;
  pass the active provider's number instead. `/dev/caller` sends Twilio-format messages and
  would need the same tweaks as the message models.

## Senior app relay (protocol v0)

See [`docs/APP_PROTOCOL.md`](../docs/APP_PROTOCOL.md). In short: the app keeps
`WS /app/control` open; when a provider stream starts, the backend sends `incoming_call` with a
one-time token (5 min); the app opens `WS /app/call/{callId}` and sends `accept`. Until then
the caller hears ringback; after it, audio is bridged (app side PCM16 LE 16 kHz, 640-byte
frames; phone side μ-law 8 kHz). Every risk assessment becomes a `risk` event; the first warn
adds a warning tone; high risk sends `verify_password` and, unless the family password
arrives as DTMF in time, ends the call with `call_ended: scam_blocked` (closing the media
stream ends the phone call; the guarded REST hang-up runs as a backup), then alerts the
trusted person. No accept within `APP_ACCEPT_TIMEOUT_SECONDS` (30) → `timeout`.

## Security and privacy

- Provider webhooks: `X-Twilio-Signature` is validated against `PUBLIC_BASE_URL + path` (the
  app runs behind a tunnel or proxy, so the Host header is not trusted). Invalid or missing
  signature: 403. Request body limited to 16 KiB, form only.
- The media stream must present a one-time token (issued by the webhook, bound to the call,
  valid 2 minutes) in its `start` message, otherwise it is closed with code 1008. The
  handshake signature is only logged until checked against a real Twilio account.
- App channels: the control channel needs `APP_DEVICE_TOKEN` (≥ 16 characters, constant-time
  comparison); the call channel needs the single-use, call-bound token from `incoming_call`.
  Token values in URLs are redacted from uvicorn's access logs (`RedactTokensFilter`).
- Messages on all sockets are validated; malformed ones are logged (error type and field only,
  never payloads) and skipped.
- Audio and transcripts live only in RAM per call and are cleared when it ends. Logs contain
  call ids, scores, categories and error types; never transcript text, audio, DTMF digits,
  the family password or full phone numbers (masked, e.g. `+48*******01`).
- Secrets are `SecretStr` and never logged; settings validation errors hide input values.
- `DEV_TOOLS=true` exposes `POST /dev/calls`, which admits calls without a provider signature:
  local use only.

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

Anything that can spend provider money goes through `GuardedCallActions`
(`app/telephony/guard.py`); `build_call_actions` always wraps the provider's REST actions.

| Guard | Setting (default) | Behaviour |
| --- | --- | --- |
| Dry run | `TELEPHONY_DRY_RUN=true` | Outbound calls, SMS and REST hang-ups are logged as `telephony_would_<action>` and not executed. Real actions only when explicitly `false`. |
| Allowlist | `OUTBOUND_ALLOWLIST=` (empty) | Comma-separated E.164 numbers. Any other destination, a malformed number or our own `TWILIO_NUMBER` (call loop) is refused and logged. |
| Daily caps | `MAX_OUTBOUND_CALLS_PER_DAY=10`, `MAX_SMS_PER_DAY=20` | Counted per UTC day in `DATA_DIR/telephony_counters.json` (date and counts only). Reserved before the action runs; survives restarts. Unreadable counter file → outbound refused (fail closed for spending). |
| Per-incident dedupe | always on | At most one REST hang-up, one trusted-person call and one SMS per incoming call, however many high readings arrive. |
| Concurrency | `MAX_CONCURRENT_CALLS=2` | Pending + active calls. Extra webhook requests get TwiML `<Say>` "protection temporarily unavailable" (PL/EN) + `<Hangup/>`; streams without a slot/token are refused. |
| Call duration | `MAX_CALL_SECONDS=600` | The stream closes itself after the limit. Closing the WebSocket ends `<Connect>`; there is no further TwiML verb, so the provider hangs up the call. |
| Rate limit | `MAX_INCOMING_CALLS_PER_MINUTE=10` | In-memory sliding window on signed webhook requests (and `POST /dev/calls`) → HTTP 429. |

Order of checks for outbound actions: number format → own number → allowlist → dedupe →
dry run → daily cap → execute. Dry-run actions do not count against the caps. The guard, the
admission state and the app hub are per process: run a single uvicorn worker.

`TRUSTED_PERSON_NUMBER` (E.164) is the person alerted on high risk; it must also be on the
allowlist. Until the family panel exists this is the only trusted person.

## Failure behaviour

- No senior app connected (control channel closed) when a call arrives, or all call slots
  busy: the caller hears "protection temporarily unavailable" and the call ends (v0; later:
  forward to the senior's phone). The app shows "protection unavailable" while its control
  channel is down.
- App call channel drops mid-call: the call ends (`error`).
- STT failure or timeout: logged (`stt_failed`), audio keeps flowing, the session is marked
  degraded. Decision model failure: rules only.
- A failing action never stops the call or the other incident steps.
- Backend down entirely: configure a Twilio fallback URL (e.g. a TwiML Bin that dials the
  senior directly) so calls still go through.

## Not done yet

- whisper.cpp HTTP client, basal-1 / Clef-Flash clients, Silero VAD (an RMS gate skips silent
  windows for now)
- Spoken warnings and a spoken family-password prompt for the caller (TTS assets); today the
  senior gets a tone and an in-app prompt
- Transcribing the senior's side (the app audio is bridged but not analysed)
- Per-senior language, family password and trusted contacts from the family panel
- Dockerfile / docker compose
