# Sprawdzam / Second Ear: backend

FastAPI service that answers forwarded calls through a telephony provider (Twilio for now),
relays the call audio to the senior's app, transcribes the caller and scores the scam risk in
real time.

```
provider ── POST /twilio/voice ──► signature, rate limit, app online?, call slot ──► TwiML:
                                    <Say> protection notice + <Connect><Stream wss://…/twilio/stream>
provider ══ WS /twilio/stream ══► μ-law 8 kHz → PCM 16 kHz ─┬─► 3–8 s speech segments → Whisper
                                                             │     → RiskEngine (basal + rules)
                                                             │     → IncidentResponder
                                                             └─► CallBridge ══ WS /app/call/{id} ══► senior app
senior app ══ WS /app/control (incoming_call, protection status) ══ AppHub
```

Status: speech-to-text (whisper.cpp `whisper-server`) and the decision model (basal-1.0-4.5B via
`basal-serve`) are wired in; without them the backend falls back to no transcript / keyword
rules. Twilio REST actions exist but run in dry-run mode by default.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.12 is pinned in `.python-version`; uv downloads it)

## Install, run, test

```bash
cd server
uv sync                                    # creates .venv with locked dependencies
scripts/run_dev.sh --reload                # http://127.0.0.1:8765/health
uv run pytest                              # full test suite, no network access needed
uv run pytest -m live                      # opt in: real whisper-server :8080 / basal-serve :8000
uv run ruff check . && uv run ruff format --check .
```

The backend's dev port is **8765** (port 8000 belongs to `basal-serve`, 8080 to
`whisper-server`). `scripts/run_dev.sh` is `uvicorn app.main:app --host 127.0.0.1 --port 8765`;
set `PORT` to change it.

Configuration comes from environment variables or a `.env` file (the repository root `.env`
first, then an optional `server/.env`). Copy `../.env.example` to `../.env`. Without
`TWILIO_AUTH_TOKEN` all Twilio webhooks are refused (403); for local experiments only, set
`ALLOW_UNSIGNED_WEBHOOKS=true`. Without `APP_DEVICE_TOKEN` the senior app cannot connect, so
every call fails open ("protection temporarily unavailable", see Failure behaviour).

## 5-minute manual test in the browser (no phone, no Twilio account)

```bash
cd server
scripts/make_prompts.sh && scripts/make_samples.sh     # once: voice prompts + sample clips
DEV_TOOLS=true APP_DEVICE_TOKEN=dev-token-change-me-123 scripts/run_dev.sh
```

1. Open <http://localhost:8765/dev/senior>, paste `dev-token-change-me-123` as the device
   token and click **Turn protection on**. "Protection: on" means the control channel is open.
   The optional **Settings** box sends `settings` (language, trusted person, whitelist).
2. Open <http://localhost:8765/dev/caller> in a second tab. Pick an **Audio source**: the
   microphone or a sample clip (`pl_scam_police`, `pl_scam_bank`, `pl_normal_family`,
   `en_scam_bank`, `en_normal_family`; the call language follows the clip). Tick **mute
   playback** if both tabs share speakers. Click **Call**. The senior tab shows the incoming
   call (masked number) and the caller tab hears the 425 Hz ringback tone.
3. Click **Accept** in the senior tab (it asks for the microphone). The ringback stops and a
   sample clip starts playing in real time through the same `/twilio/stream` path.
4. With the models running, watch the risk bar rise; a scam ends with the password prompt and
   `call_ended: scam_blocked`. A normal clip stays below the warning level.
5. Click **Hang up** in either tab; the other side shows the call as ended.

Without `WHISPER_URL` there is no transcript, so the risk bar stays at 0. The browser needs a
secure context for the microphone: `http://localhost` works, a LAN IP needs HTTPS (e.g. a
tunnel). Sample mode needs no microphone. Not accepting within 30 s ends the call
(`timeout`). The caller keypad sends DTMF (the family password). `/dev/caller` speaks the
Twilio media stream format over the same WebSocket the real provider uses.

## Dev backend for the end-to-end test with the HarmonyOS app

Dev values live in the untracked `server/.env.dev` (ignored by `.env.*`): `DEV_TOOLS=true`,
`APP_DEVICE_TOKEN=dev-device-1-sprawdzam`, `FAMILY_PASSWORD=1234` (**demo value only**),
`TELEPHONY_DRY_RUN=true`, models on `127.0.0.1:8080` / `:8000`.

```bash
cd server
nohup scripts/run_dev.sh --env .env.dev > ~/models/sprawdzam/logs/backend.log 2>&1 &
# restart: pkill -f "uvicorn app.main:app --host 127.0.0.1 --port 8765", then the line above
```

- Caller: <http://localhost:8765/dev/caller> · stand-in app: <http://localhost:8765/dev/senior>
  · status: <http://localhost:8765/health>
- The emulator reaches the Mac with `hdc rport tcp:8765 tcp:8765`; the app connects to
  `ws://localhost:8765/app/control?device_token=dev-device-1-sprawdzam`.
- Log: `~/models/sprawdzam/logs/backend.log` (no transcripts, numbers masked).

## Docker deployment (written, not yet run)

`server/Dockerfile` (python:3.12-slim, uv-locked dependencies, non-root user, one worker),
`deploy/docker-compose.yml` (backend + Caddy) and `deploy/Caddyfile` (automatic HTTPS for
`DOMAIN`, WebSocket proxying, `/dev/*` blocked, no access log because URLs carry tokens):

```bash
# repository root, with .env filled in (DOMAIN, Twilio, APP_DEVICE_TOKEN, ...)
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
```

Models stay outside the containers: on the Mac the backend reaches them through
`host.docker.internal` (start them with `WHISPER_HOST=0.0.0.0` / `BASAL_HOST=0.0.0.0` if
Docker cannot reach the localhost-bound servers); on AWS set `DOCKER_WHISPER_URL` /
`DOCKER_BASAL_URL` to the model host. `docker compose config` validates the files; the image
has not been built yet (no Docker daemon on the hackathon network).

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness, provider, app connection, backends and limits. No secrets or numbers. |
| `POST /twilio/voice` | Provider incoming-call webhook. Returns TwiML. |
| `WS /twilio/stream` | Provider bidirectional media stream for one call. |
| `WS /app/control?device_token=…` | Senior app control channel (protocol v0). |
| `WS /app/call/{callId}?token=…` | Senior app call channel: audio + risk events (protocol v0). |
| `GET /dev/caller`, `GET /dev/senior`, `POST /dev/calls` | Browser test tools, only with `DEV_TOOLS=true`. |
| `WS /dev/events`, `GET /dev/alerts` | Live call events for the jury / operator console and the last 50 alert summaries (RAM only), only with `DEV_TOOLS=true`. Schema below. |

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

Settings from the app (`settings` on the control channel, see the protocol): `lang` sets the
language of the next calls; calls from numbers on the `whitelist` are bridged without the
notice, speech-to-text or risk analysis (`incoming_call.trusted = true`); `trustedPerson`
becomes the alert target only if it is on `OUTBOUND_ALLOWLIST`, otherwise
`TRUSTED_PERSON_NUMBER` is used. Settings live in RAM only and are logged as counts.

Connecting the HarmonyOS app (emulator) in development: run the backend on 8765, forward the
port with `hdc rport tcp:8765 tcp:8765`, and use the same device token in the app and in the
backend (`APP_DEVICE_TOKEN`, at least 16 characters; the dev backend above uses
`dev-device-1-sprawdzam`, the shorter `dev-device-1` is rejected with 1008). The app derives the call URL from the control
URL (`/app/control` → `/app/call/{callId}?token=…`), as in the protocol.

See [`docs/APP_PROTOCOL.md`](../docs/APP_PROTOCOL.md). In short: the app keeps
`WS /app/control` open; when a provider stream starts, the backend sends `incoming_call` with a
one-time token (5 min); the app opens `WS /app/call/{callId}` and sends `accept`. Until then
the caller hears ringback; after it, audio is bridged (app side PCM16 LE 16 kHz, 640-byte
frames; phone side μ-law 8 kHz). Every risk assessment becomes a `risk` event; the first warn
adds a warning tone; high risk sends `verify_password` (`timeoutSeconds`,
`PASSWORD_TIMEOUT_SECONDS`, default 12) or, without a `FAMILY_PASSWORD`, `confirm_block`
(`seconds`, `AUTO_BLOCK_SECONDS`, default 8) and, unless the family password arrives as DTMF
in time, ends the call with `call_ended: scam_blocked` (closing the media
stream ends the phone call; the guarded REST hang-up runs as a backup), then asks the
senior's phone to text the trusted person (`alert_trusted` on the control channel, once per
call, queued 2 min if the app is offline; the app answers `alert_trusted_result`). The
backend's own Twilio call/SMS to `TRUSTED_PERSON_NUMBER` still runs through the guard (dry-run
in the demo). No accept within `APP_ACCEPT_TIMEOUT_SECONDS` (30) → `timeout`. A senior
`hangup` during the password / confirm stage, or while the model's own score is sustained at
or above `RISK_HANGUP`, ends the call as `scam_blocked` (same alert path, action
`senior_blocked`); during a warning only it stays `senior_hangup`.

The senior's microphone audio is also transcribed (speaker "senior", see below).

## Operator console events (`WS /dev/events`)

`app/events.py` is an in-process pub/sub. Publishing never blocks the call pipeline: every
subscriber has a bounded queue (256) and loses its oldest events when it falls behind; a page
that stops reading for 5 s is disconnected. Server → page JSON (fields are only ever added):

```
{"type":"hello","warn":50,"hangup":90,"alerts":[<alert>...]}                 on connect
{"type":"call_started","callId","at","caller":"+48 *** *** 123","lang"}
{"type":"transcript","callId","at","speaker":"caller"|"senior","text"}
{"type":"risk","callId","at","score","modelScore","rulesScore","level":"none|warn|high",
 "scamType","reasons":[...],"source":"model+rules"|"rules"}
{"type":"action","callId","at","action","detail"}
   action: warn | verify_password | password_ok | password_failed | confirm_block |
           senior_blocked | hangup | sms_requested | sms_sent | sms_failed | fail_open
{"type":"call_ended","callId","at","reason","alert":<alert>|null}
<alert> = {"callId","at","caller","scamType","maxScore","outcome":"warned|blocked|normal","actions":[...]}
```

`at` is ISO 8601 UTC with milliseconds. `score` is the smoothed combined score, `modelScore`
is `null` when the model did not answer. `alert` is `null` for whitelisted calls and calls
that never got a risk reading. Alerts never contain transcript text; transcript events exist
only on the live stream (never stored or logged). `fail_open` and late `sms_*` actions may
arrive for a call id without `call_started` / after `call_ended`.

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

## Speech-to-text and decision model

Both models run natively on the Mac (see `server/bench/README.md`:
`server/bench/run-whisper.sh`, `server/bench/run-basal.sh`). Set in `.env`:
`WHISPER_URL=http://127.0.0.1:8080`, `DECISION_BACKEND=basal`, `BASAL_URL=http://127.0.0.1:8000`
(a backend in Docker uses `http://host.docker.internal:…`). At start-up the backend sends one
warm-up request to each (the first basal decision compiles kernels, ~2 s); `/health` shows
`models.*.warmup`.

- **Segmentation** (`app/audio/segmenter.py`): the caller's 16 kHz audio is cut at pauses
  (≥ `STT_PAUSE_SECONDS`, 0.2 s, energy VAD) into 3–8 s segments; short utterances go out after
  a 1 s pause; silence is never sent. Whisper's latency hardly depends on segment length and
  2 s chunks hurt accuracy. Silero VAD is the planned upgrade for noisy lines. The senior's
  microphone (from the app) has its own segmenter, 1.5–5 s (`STT_SENIOR_MIN_SEGMENT_SECONDS`,
  `STT_SENIOR_MAX_SEGMENT_SECONDS`; `ANALYSE_SENIOR=false` turns it off) with an adaptive
  threshold: on a speakerphone with echo cancellation and AGC the level between words stayed
  above the fixed -40 dBFS, so every senior segment ran to the 8 s maximum. The senior
  threshold is the highest of -40 dBFS, 6 dB over the noise floor (quietest 20 ms frame of
  the last 2 s) and 16 dB under the speaker's running speech level. `LOG_LEVEL=DEBUG` logs
  every cut (`segment_cut`: reason, length, mean RMS, noise floor, speech level, threshold).
- **One STT worker per call** (`app/session.py`): Whisper is one shared server, so caller and
  senior segments go through one sequential queue with the caller first. A senior segment
  waits while the caller is mid-utterance (up to 8 s), is skipped when older than 12 s and
  gets a 3 s timeout. Logs: `stt_latency` with `speaker` and `queue_wait_ms`.
- **Echo guard** (`app/echo_guard.py`): the phone's speaker (caller voice, our voice prompts)
  leaks into its microphone. A senior utterance similar to (difflib ratio ≥ 0.75), contained
  in, or made of the words of a caller utterance / prompt from the 15 s before it was
  captured is dropped (`echo_dropped`). In a longer segment that mixes echo with the senior's
  own words, runs of ≥ 3 words found in the same order in the recent caller text (caller
  utterances concatenated) are removed and the rest is kept (`echo_trimmed`).
- **Whisper client** (`app/stt/whisper.py`): `POST /inference` with a 16 kHz PCM16 WAV,
  `language` forced from the call, `verbose_json`, `temperature=0.0`. Segments with
  `no_speech_prob > 0.6` and known silence hallucinations ("KONIEC", "Napisy wykonane…",
  "Dziękuję za uwagę", "Thank you for watching") are dropped. Timeout 5 s (measured 0.5–1 s
  alone, ~2.2 s while basal is busy on the same GPU); errors skip the segment (`stt_failed`)
  and the call goes on.
- **basal client** (`app/risk/basal.py`, schemas in `app/risk/schemas/`): state = the last
  60 s of transcript with speaker tags (`Dzwoniący:` / `Caller:` and `Senior:`),
  PL or EN schema from the call language. Every new segment asks `risk` + `scam_type`
  (~1.1 s); the first evaluation after a reading ≥ `RISK_WARN` asks all six questions once
  (~2 s) and caches `money`/`secrecy`/`authority`/`urgency`. Model score =
  `100·(1 − P(low))`. Timeout 3 s; a timeout, HTTP error (incl. 422 `{"error"}`) or
  malformed / out-of-range answer means rules only for that reading
  (`decision_fallback_to_rules`).
- **Keyword rules** (`app/risk/rules.py`): Polish and English phrases on normalised text,
  including amounts written as digits (`30 tysięcy`, `200 zł`, `$500`) and six-digit codes
  near "kod"/"BLIK"/"code". Single words score low; combinations score high.
- **Scoring** (team decision): combined = max(model, rules). Warn when the combined score is
  ≥ `RISK_WARN` (50) for two readings in a row. Family-password check, then hang-up, only when
  the **model's own score** is ≥ `RISK_HANGUP` (90) for two readings in a row **and** (cached secrecy ≥ `SECRECY_HANGUP_MIN` (0.8) or a keyword-rule
  hit: a secrecy phrase or a rules score ≥ `RISK_WARN`). Actions only escalate. The rules
  cannot read negation ("a bank never asks for BLIK"), so on their own they can warn but never
  hang up: with the model down (source `rules`) the engine reaches at most `warn`, and a
  reading without a model answer breaks the model's two-reading streak.
  `DECISION_FULL_REFRESH_SECONDS` (default 10, 0 = once per call) re-asks the six questions
  at most that often while the hang-up gate is blocked only by an early, low secrecy answer.
- Logs carry per-segment `stt_latency` and per-request `decision_latency` (ms), scores and
  categories; never transcript text.

### Voice prompts (local step, not committed)

```bash
cd server && scripts/make_prompts.sh      # macOS `say` (Zosia / Samantha) + ffmpeg
```

Writes `DATA_DIR/prompts/{warning,password,blocked}_{pl,en}.ulaw` (8 kHz μ-law, phone
band-pass) from the texts in `app/prompts.py`. The audio is not committed (Apple voice
licensing). The senior hears `warning` on the first warn; caller and senior hear `password`
before the DTMF check (the senior hears `warning` first if there was no warn step); the caller
hears `blocked` before a blocked call ends. While a prompt plays to one side, live audio to
that side is muted, and prompts are paced in real time. Missing files → beep tones and a
`voice_prompt_missing` log line; `/health` lists which prompts exist. Without
`FAMILY_PASSWORD` there is no password prompt: the app gets `confirm_block` and the call is
blocked after `AUTO_BLOCK_SECONDS` (8).

### End-to-end smoke test with the real models

```bash
cd server
DEV_TOOLS=true APP_DEVICE_TOKEN=smoke-device-token-123456 scripts/run_dev.sh   # terminal 1
APP_DEVICE_TOKEN=smoke-device-token-123456 uv run python scripts/smoke_call.py \
    --audio ~/models/sprawdzam/audio/pl_scam_police_8k_ulaw.wav --lang pl     # terminal 2
```

The script plays the senior app (control + call channel, `accept`) and the caller (a WAV
streamed in real time over `/twilio/stream`) and prints the timeline of `risk`,
`verify_password` and `call_ended` events. Clips come from the model bench
(`server/bench/stt/make_audio.sh`). It also prints a summary of `/dev/events` (counts,
speakers, actions, alert) and answers `alert_trusted` (expected once for a blocked call).
`--echo-gain 0.7` loops the caller audio the app receives back as its microphone (echo
test); `--senior-audio WAV --senior-at 30` plays a clip as the senior's speech;
`--senior-noise -45` adds a noise floor (dBFS). With any of the three the microphone is one
continuous 20 ms stream mixing noise, echo and the clip, as on a phone. Run it against
your own backend port (`--base http://127.0.0.1:<PORT>`), and keep `--tail-seconds` long
enough to cover the password window (12 s) or the confirm countdown (8 s).

## Telephony cost and safety guard

Anything that can spend provider money goes through `GuardedCallActions`
(`app/telephony/guard.py`); `build_call_actions` always wraps the provider's REST actions.

| Guard | Setting (default) | Behaviour |
| --- | --- | --- |
| Dry run | `TELEPHONY_DRY_RUN=true` | Outbound calls, SMS and REST hang-ups are logged as `telephony_would_<action>` and not executed. Real actions only when explicitly `false`. |
| Allowlist | `OUTBOUND_ALLOWLIST=` (empty) | Comma-separated E.164 numbers. Any other destination, a malformed number or our own `TWILIO_NUMBER` (call loop) is refused and logged. |
| Daily caps | `MAX_OUTBOUND_CALLS_PER_DAY=10`, `MAX_SMS_PER_DAY=20` | Counted per UTC day in `DATA_DIR/telephony_counters.json` (date and counts only). Reserved before the action runs; survives restarts. Unreadable counter file → outbound refused (fail closed for spending). |
| Per-incident dedupe | always on | At most one REST hang-up, one trusted-person call and one SMS per incoming call, however many high readings arrive. |
| Concurrency | `MAX_CONCURRENT_CALLS=2` | Pending + active calls. Extra webhook requests fail open (see Failure behaviour); streams without a slot/token are refused. |
| Call duration | `MAX_CALL_SECONDS=600` | The stream closes itself after the limit. Closing the WebSocket ends `<Connect>`; there is no further TwiML verb, so the provider hangs up the call. |
| Rate limit | `MAX_INCOMING_CALLS_PER_MINUTE=10` | In-memory sliding window on signed webhook requests (and `POST /dev/calls`) → HTTP 429. |

Order of checks for outbound actions: number format → own number → allowlist → dedupe →
dry run → daily cap → execute. Dry-run actions do not count against the caps. The guard, the
admission state and the app hub are per process: run a single uvicorn worker.

`TRUSTED_PERSON_NUMBER` (E.164) is the person the backend itself calls / texts on a blocked
scam; it must also be on the allowlist (the app's `trustedPerson` takes precedence when
allowlisted). In the demo the SMS is sent by the senior's phone instead (`alert_trusted`).

## Failure behaviour

- No senior app connected (control channel closed) when a call arrives, or all call slots
  busy: **fail-open**. With `SENIOR_NUMBER` set, on `OUTBOUND_ALLOWLIST` and
  `TELEPHONY_DRY_RUN=false`, the caller hears "protection temporarily unavailable, connecting
  without protection" (PL/EN) and Twilio `<Dial>`s the senior's own number. Without that
  route (unset, not allowlisted, dry-run) the caller hears a neutral "protection temporarily
  unavailable" and the call ends. Logged as `fail_open_route` (route, never the number) and
  published as a `fail_open` console event; `POST /dev/calls` answers 503 with
  `failOpen: true`. Implemented and unit-tested; the `<Dial>` path has not been tried with a
  real call. The app shows "protection unavailable" while its control channel is down.
- App call channel drops mid-call: the call ends (`error`).
- STT failure or timeout: logged (`stt_failed`), audio keeps flowing, the session is marked
  degraded. Decision model failure: rules only.
- A failing action never stops the call or the other incident steps.
- Backend down entirely: configure a Twilio fallback URL (e.g. a TwiML Bin that dials the
  senior directly) so calls still go through.

## Not done yet

- Silero VAD instead of the energy rule; Clef-Flash client
- Threshold tuning on `scenarios/` (the evaluation agent's results)
- Family password from the senior app (language, trusted person and whitelist already come
  from its `settings`; the password still comes from `.env`; no family web panel is planned)
- Measuring the effect of the senior's transcript on false warnings with real calls
- `/dev/events` is a dev route (DEV_TOOLS); a production operator console would need auth
