# Architecture

Sprawdzam (Second Ear) listens to phone calls from unknown numbers while they happen, turns the speech into
text, estimates how likely the call is a scam and, when the risk is high, asks for the family password, ends
the call and alerts a trusted person. This document describes what is **built** (backend, app, demo tools) and
two deployment variants that are **designed, not built**: a module at a mobile operator (the B2B product) and a
B2C pilot with call forwarding.

Status words used below: **built** = in the repository and covered by tests or run by us; **in progress** =
being built on 4 Oct 2026 on another branch; **designed, not built** = described here only.

Related documents: [`AI_FEATURES.md`](AI_FEATURES.md) (models, evaluation, privacy),
[`APP_PROTOCOL.md`](APP_PROTOCOL.md) (backend ⇄ app protocol v0), [`../server/README.md`](../server/README.md)
(backend details, endpoints, configuration), [`../server/bench/README.md`](../server/bench/README.md) (model
latency), [`../app/README.md`](../app/README.md) (app build and native modules).

## 1. Overview (as built)

```
                         ┌──────────────────────────── backend (FastAPI, one uvicorn worker) ───────────────────────────┐
call source              │                                                                                              │
 • Twilio <Connect>      │  POST /twilio/voice ─► signature, rate limit, app online?, call slot ─► TwiML notice + Stream │
   <Stream> (dry-run)    │                                                                                              │
 • /dev/caller "operator │  WS /twilio/stream ─► μ-law 8 kHz ─► PCM 16 kHz ─┬─► PauseSegmenter (3–8 s) ─► Whisper      │
   network simulator"    │    (Twilio media    (g711 + soxr)                │      ─► TranscriptWindow (60 s, RAM)      │
   via POST /dev/calls   │     stream format)                               │      ─► CallRiskMonitor: basal-1 + rules  │
                         │                                                  │         ─► ScoreSmoother ─► IncidentResponder
                         │                                                  └─► CallBridge ══ WS /app/call/{id} ══╗      │
                         │  WS /app/control ══ AppHub (incoming_call, protection_status, settings) ══════════════╣      │
                         └─────────────────────────────────────────────────────────────────────────────────────╫──────┘
                                                                                                                ║
                          whisper-server :8080 and basal-serve :8000 run natively on the Mac (Metal / MPS)      ║
                                                                                                                ▼
                                                                                         senior app (React Native, Android)
```

## 2. Backend components (`server/app/`)

| Module | Responsibility | Status |
| --- | --- | --- |
| `telephony/provider.py`, `twilio/` | `TelephonyProvider` interface: webhook auth and parsing, call-control markup (TwiML), media-stream message parsing, REST actions (hang-up, call, SMS). `TwilioProvider` is the only implementation; SignalWire differences are documented in `server/README.md` | Built; Twilio never run against a real account; demo runs in `TELEPHONY_DRY_RUN=true` |
| `calls/webhook.py`, `calls/intake.py`, `telephony/admission.py` | Incoming call: rate limit, "is the senior app online?", concurrency slot, one-time stream token (2 min), protection notice | Built |
| `calls/stream.py` | One media stream per call: validates the `start` message and token, feeds audio, enforces `MAX_CALL_SECONDS` | Built |
| `audio/` | G.711 μ-law codec, streaming resampler 8 ↔ 16 kHz (soxr), framing; `segmenter.py` cuts 3–8 s segments at pauses (energy VAD, never sends silence) | Built (Silero VAD planned, not built) |
| `stt/whisper.py` | Client for `whisper-server` (`POST /inference`, language forced from the senior's setting, `verbose_json`); drops `no_speech_prob > 0.6` and known silence hallucinations; timeout 5 s | Built |
| `session.py`, `transcript.py` | Per-call pipeline in RAM; STT and scoring run in a background worker so a slow model never stalls the audio; rolling 60 s speaker-tagged window | Built (caller side only; senior side **in progress**) |
| `risk/basal.py`, `risk/schemas/` | basal-1 client: every new segment asks `risk` + `scam_type`; after the first warn-level reading the six-question schema once (money, secrecy, authority, urgency, scam_type, risk); model score = `100·(1 − P(low))`; timeout 3 s | Built |
| `risk/rules.py` | 55 PL/EN regular-expression rules (money incl. digits such as `30 tysięcy`, secrecy, authority, urgency, story context) | Built |
| `risk/engine.py`, `risk/smoothing.py` | Combined score = max(model, rules). Warn: ≥ 50 two readings in a row. Family password then hang-up: ≥ 90 two readings in a row **and** (model secrecy ≥ 0.8 or a rule hit). Actions only escalate. Model failure → rules only for that reading | Built; "rules alone may warn but never hang up" is **in progress** |
| `telephony/responder.py`, `calls/voice_prompts.py` | `IncidentResponder`: `risk` event to the app on every reading; warn → spoken warning to the senior; high → spoken password request, DTMF check, blocked notice, end of call (`scam_blocked`), REST hang-up as backup, call + SMS to the trusted person | Built (trusted-person call/SMS via provider only in dry-run) |
| `telephony/guard.py` | Cost and safety guard for anything that spends money: dry-run default, outbound allowlist, daily caps, one action of each kind per call | Built |
| `calls/bridge.py`, `relay/` | `CallBridge` relays audio both ways (phone side μ-law 8 kHz, app side PCM16 16 kHz, 20 ms frames), plays prompts, mutes live audio during prompts; `AppHub` and protocol v0 (control + call WebSockets) | Built |
| `health.py`, `warmup.py` | `/health` (no secrets or numbers), one warm-up request to each model at start-up | Built |
| `dev/` | `DEV_TOOLS=true` only: `/dev/caller` (operator network simulator, sends Twilio-format media over the same `/twilio/stream` path; sample scripts or microphone), `/dev/senior` (browser stand-in for the app), `POST /dev/calls` (admits a call without a provider) | Built |
| `/dev/jury` + events stream | Projector page: live transcript of both sides, risk chart with thresholds 50 and 90, reasons and scam type, actions; second tab "operator console" with alerts only, no conversation content; marked "demo mode, call content is not shown in production" | **In progress** |

Tests: `cd server && uv run pytest` (287 passed on `main` on 4 Oct 2026, no network or models needed; fakes for
STT, the decision model, the provider REST API and the app). `uv run pytest -m live` runs against the real
model servers.

## 3. Models

| Model | Serving | Measured on Apple M4 Pro, 48 GB ([`server/bench/README.md`](../server/bench/README.md)) |
| --- | --- | --- |
| Whisper large-v3-turbo | `whisper-server` (whisper.cpp 1.9.4, Metal), `server/bench/run-whisper.sh`, port 8080 | ~0.5 s per 2–4 s chunk (p95 0.58 s) |
| basal-1.0-4.5B | `basal-serve` in MPS mode with our `--share-state` patch, `server/bench/run-basal.sh`, port 8000 | `risk` alone 0.76 s, `risk` + `scam_type` 1.07 s, six questions 1.94 s (p50); peak memory 10.3 GB |
| basal-1.0-1.5B (fallback, not default) | same server, other port | `risk` alone 0.27 s, six questions 0.65 s; 4.9 GB |

Both servers bind to `127.0.0.1`. Evaluation on 300 synthetic transcripts written by a language model is in
[`../server/bench/eval/RESULTS.md`](../server/bench/eval/RESULTS.md) and summarised in
[`AI_FEATURES.md`](AI_FEATURES.md).

## 4. Senior app (`app/`)

- React Native 0.77.1 (TypeScript), one code base. Screens: home (one big status), full-screen incoming call,
  in-call (risk banner, family-password keypad), call result, hidden settings. PL and EN strings.
- **Android** (demo device): native `CallEngine` TurboModule in Kotlin (`app/android/.../callengine/`): OkHttp
  WebSockets for the control and call channels, `AudioRecord` / `AudioTrack` in voice-communication mode,
  notifications, contact picker for the trusted person and the whitelist, `CallScreeningService` stub (allows
  all calls today). Audio frames never cross the JS bridge. Sending the alert SMS from the senior's phone
  (`SmsManager`, runtime `SEND_SMS`) after `call_ended: scam_blocked` is **in progress**.
- **HarmonyOS** (secondary port, **frozen** on 4 Oct 2026): RNOH 0.77.75, the same TurboModule in ArkTS (Audio
  Kit, Network Kit, Notification Kit, Contacts Kit picker, Asset Store Kit, Call Service Kit behind a developer
  toggle), min API 20 / target API 24, run on the DevEco emulator. Build notes in `app/README.md`.

## 5. Failure behaviour

| Failure | Behaviour |
| --- | --- |
| Decision model timeout (3 s), HTTP error, malformed or out-of-range answer | Logged as `decision_fallback_to_rules`; that reading uses the rules only |
| Whisper error or timeout | Logged (`stt_failed`), audio keeps flowing, session marked degraded; no new text, so no new escalation |
| One spiking reading | At most a warning; a hang-up needs two consecutive readings ≥ 90 plus a secrecy or rule signal |
| A failing incident step (hang-up, SMS, call) | Logged; the other steps still run |
| Senior app not connected | App shows "protection temporarily unavailable"; the backend refuses the call with a spoken notice. Target behaviour is **fail-open** (the call reaches the senior unprotected): in the B2C pilot through the provider's fallback URL, at the operator by simply not intervening. Not built |
| Backend down | Same fail-open target via provider/operator configuration. Not built |

## 6. Security and privacy (as built)

- **Transport**: production URLs are `wss://` / `https://` (Caddy with automatic HTTPS in `deploy/`, written,
  not yet run; in the demo a Cloudflare quick tunnel). `ws://` only on localhost during development.
- **Provider webhooks**: `X-Twilio-Signature` checked against `PUBLIC_BASE_URL + path`; body limit 16 KiB;
  media stream must present a one-time, call-bound token (2 min) in its `start` message.
- **App channels**: control channel needs `APP_DEVICE_TOKEN` (≥ 16 characters, constant-time comparison);
  call channel needs a single-use, call-bound token (5 min) from `incoming_call`. Tokens are redacted from
  access logs.
- **RAM only**: audio and transcripts live in the per-call session and are dropped when the call ends. Logs
  carry call ids, scores, categories and error types; never transcript text, audio, DTMF digits, the family
  password or full phone numbers (masked).
- **No emotion recognition, no voice biometrics**: the decision model sees text only (EU AI Act).
- **Secrets** in `.env` (template `.env.example`), `SecretStr`, never logged. `DEV_TOOLS` pages are blocked by the
  Caddy config and must never be enabled in production.

## 7. Target deployment at a mobile operator

> **Status: designed, not built.** Nothing in this section has been implemented or tested with an operator. It
> describes how the built backend would be adapted. Legal points are an outline to be confirmed with lawyers,
> not legal advice.

### 7.1 Idea

The operator runs the Sprawdzam module in its own data centre. For subscribers who switched the service on, the
module receives a **copy** of the audio of calls from numbers the subscriber does not know, analyses it while
the call goes on and triggers alerts. The subscriber installs nothing and the call path is not changed: the
module listens to a copy and only acts (warning tone, password prompt, ending the call) through the operator's
call-control interfaces.

```
caller ──► operator core (VoLTE / IMS) ──────────────► subscriber's phone      (call unchanged)
                 │
                 │ media fork: copy of both audio legs
                 ▼    (IMS application server, or SIPREC RFC 7866 from the session border controller)
        Sprawdzam module (Docker, operator data centre)
          SIPREC / RTP intake ─► the built pipeline: 16 kHz PCM ─► segments ─► Whisper ─► basal-1 + rules
                 │
                 ├─► call control via the IMS application server: warning tone, family password, release the call
                 ├─► SMS to the trusted person from the operator's SMSC
                 └─► aggregated campaign signals (no call content) ─► operator fraud team
```

### 7.2 Components

| Component | Design | Reuses from the build |
| --- | --- | --- |
| Packaging | Docker images (backend, Whisper, decision model) on GPU nodes in the operator's network; no traffic leaves it | `server/Dockerfile`, `deploy/docker-compose.yml` (Kubernetes or the operator's platform later) |
| Audio intake | Either an IMS application server in the call path that forks media, or a **SIPREC (RFC 7866)** recording session from the session border controllers (SBC), which sends both legs as RTP plus call metadata | New `TelephonyProvider` implementation (SIPREC/RTP instead of Twilio Media Streams); everything after the 16 kHz conversion is unchanged |
| Who is analysed | Only subscribers who opted in, and only calls from numbers not in the subscriber's call history or contacts (the operator can derive "known" numbers from call history; a contact list needs the subscriber's consent or the app) | Whitelist / `trusted` bypass already exists per device (`settings.whitelist`) |
| Actions | Warning tone and password prompt injected into the call; release of the call through the application server; SMS to the trusted person from the operator's SMSC | `IncidentResponder`, `GuardedCallActions`; voice prompts |
| Campaign signals | Aggregates such as "number X called N opted-in subscribers in an hour, M of them scored ≥ 90", scam type counts; shared with the operator's fraud team (and, if agreed, CERT/police) **without call content** | Scores and scam types already exist per call; aggregation not built |
| Operator console | Alerts list (time, masked numbers, score, scam type, actions), no transcript | The "operator console" tab of `/dev/jury` (**in progress**) is the demo version |

### 7.3 Capacity and latency (rough estimate)

> Rough estimate from our measurements on one Apple M4 Pro laptop; not measured on server GPUs, without batching.

- Per analysed call the expensive work is one Whisper request per 3–8 s speech segment (~0.5 s) plus one basal
  reading per segment (`risk` + `scam_type`, ~1.07 s), i.e. roughly 1.6 s of accelerator time per segment, or
  about 0.2–0.5 s per second of speech for one side of the call.
- On the laptop both models share one GPU and requests are served one at a time, so a single machine handles a
  **few concurrent calls**. The demo backend is configured for `MAX_CONCURRENT_CALLS=2`.
- At operator scale this needs request batching on data-centre GPUs and a smaller model where it is good
  enough (basal-1.0-1.5B is ~3× faster but scores less sharply, see `AI_FEATURES.md`). Only calls from unknown
  numbers to opted-in subscribers are analysed, which limits the load. Sizing must be measured, not extrapolated.
- Latency: in the turn-by-turn replay on synthetic data a warning came after a median of ~12 s of speech and the
  hang-up path after a median of ~22 s (`server/bench/eval/RESULTS.md`); model latency adds ~1–2 s per reading.

### 7.4 Legal basis (outline, to be confirmed with lawyers)

| Topic | Design assumption | Open question |
| --- | --- | --- |
| Consent | Explicit opt-in by the subscriber (or a legal guardian), revocable at any time; the caller is told at the start that the call is checked for fraud and not recorded | Whether informing the caller is sufficient for the caller's side of the conversation |
| GDPR minimisation | Audio and transcript in RAM only, 60 s window, deleted at call end; only an alert summary (time, score, scam type, signals, actions) is stored; numbers masked in logs | Retention period of alert summaries and campaign aggregates |
| Telecom secrecy | Processing inside the operator's network, by the operator or its processor, for a service the subscriber asked for | How Polish telecom law (secrecy of communications) applies to automated content analysis with consent; to be confirmed |
| AI Act | No emotion recognition, no biometric identification; text-only analysis with a human-facing warning | Risk classification of the system as a whole |

## 8. B2C pilot with call forwarding and routing

> **Status: designed, not built.** The backend today supports **one** senior device per deployment
> (`APP_DEVICE_TOKEN`) and does not read forwarding headers. Nothing below is implemented yet.

In the pilot the senior uses the Android app and the operator's ordinary call forwarding. The phone rejects
unknown numbers (`CallScreeningService`), the operator forwards rejected calls ("on busy") to a Sprawdzam
number, the backend answers, analyses the call and relays it to the app (the built path in section 1).

**Problem:** with many seniors, one shared virtual number receives many concurrent forwarded calls, and the
backend must know which senior each call belongs to. Matching strategies, in order:

| # | Strategy | How | Notes |
| --- | --- | --- | --- |
| 1 | Forwarding header from the provider | Twilio passes the forwarding subscriber as `ForwardedFrom`; SIP trunks carry it in the `Diversion` or `History-Info` header. Look up the senior by that number | Best case; depends on the operator passing the header through |
| 2 | Report from the app | When the app rejects a call it sends the backend "I rejected +48…, at hh:mm:ss" over the control channel; the backend matches the forwarded call by caller number and a short time window (a few seconds) | Works when the header is missing; ambiguous if the same number calls two seniors at the same second (then refuse to guess and fall back to 3 or fail-open) |
| 3 | Dedicated number per customer | Each senior forwards to their own virtual number; the number identifies the senior | Always works; costs one number per customer |

Required backend changes (not built): multiple devices (one control channel and token per senior), a lookup
from senior number to device, the app's `rejected_call` message (a protocol extension), and per-senior settings
(language, trusted person, family password) instead of `.env` values.
