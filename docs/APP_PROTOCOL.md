# App protocol v0 (backend ⇄ senior app)

Status: **v0**, implemented by the backend in `server/app/relay/`. The senior app (React Native,
HarmonyOS + Android) and the browser stand-in `/dev/senior` implement the client side.
Changes to this document must be agreed by both sides.

## Overview

Two WebSocket channels:

| Channel | URL | Lifetime |
| --- | --- | --- |
| Control | `WS /app/control?device_token=<APP_DEVICE_TOKEN>` | Open the whole time protection is on |
| Call | `WS /app/call/{callId}?token=<one-time token>` | One per protected call |

Production URLs use `wss://` (TLS). `ws://` is only for local development.

```
caller ─► provider (Twilio) ─► backend ──control──► app: incoming_call {callId, token}
                                       ◄──call──── app connects /app/call/{callId}?token=…
caller hears ringback ............... ◄──call──── {"type":"accept"}
caller audio  ═══════════════════════ call ═════► app speaker   (PCM16 16 kHz)
caller ◄═════ senior audio ══════════ call ◄═════ app microphone (PCM16 16 kHz)
                                       ──call───► risk events, verify_password, call_ended
```

General rules for both channels:

- Text frames carry one JSON object with a `type` field. Unknown `type` values and unknown
  fields must be ignored (forward compatibility). Invalid JSON is ignored by the backend.
- Strings are UTF-8. `callId` is an opaque string (letters, digits, `_`, `-`; at most 64
  characters). Do not parse it.
- Close codes used by the backend:

| Code | Meaning |
| --- | --- |
| 1000 | Normal close (call ended, server shutdown) |
| 1008 | Authentication or policy failure (bad device token, bad/used/expired call token) |
| 4000 | Control channel idle: no message for 45 s |

## 1. Control channel

`WS /app/control?device_token=<APP_DEVICE_TOKEN>`

- `APP_DEVICE_TOKEN` is a long random secret configured on the backend (env) and in the app.
  v0 supports one senior device per backend; several control connections with the same token
  are allowed (e.g. the app and `/dev/senior`), and all of them get every notification.
- A wrong or missing token, or a backend without a configured token: the socket is accepted
  and immediately closed with **1008**.

### Backend → app

```json
{"type": "protection_status", "available": true}
```
Sent right after the connection is accepted, and with `"available": false` when the backend
shuts down. While the control channel is closed or reconnecting, the app shows
**"protection unavailable"**.

```json
{"type": "incoming_call", "callId": "CA1f…", "token": "pK3…", "caller": "+48 *** *** 123", "lang": "pl"}
```
A protected call has reached the backend. `token` is single use and valid for **5 minutes**
(it opens the call channel once). `caller` is a masked number for display only (`"unknown"`
when the number is hidden). `lang` is `"pl"` or `"en"`. The app should open the call channel
**immediately** (before the senior answers) and show the ringing screen.

```json
{"type": "pong"}
```
Answer to `ping`.

### App → backend

```json
{"type": "ping"}
```
Every **15 s**. The backend closes the control channel with **4000** if it receives no message
for **45 s**. The app reconnects with backoff (e.g. 1 s, 2 s, 5 s, then every 10 s).

## 2. Call channel

`WS /app/call/{callId}?token=<token from incoming_call>`

- The token is bound to `callId`, valid 5 minutes and **single use**: a second connection with
  the same token, a wrong token, an expired token or a call that has already ended → **1008**.
- Binary frames carry audio, text frames carry JSON.

### Audio (binary frames, both directions)

- PCM, signed 16-bit **little-endian**, **mono**, **16 kHz**.
- **20 ms per frame = 320 samples = 640 bytes**. The backend accepts any even frame size up to
  200 ms (6400 bytes) and drops odd-sized or larger frames.
- Backend → app: the caller's voice (only after `accept`) and backend sounds such as the
  warning tone. Play it as it arrives with a small jitter buffer (40–100 ms).
- App → backend: the senior's microphone, only after `accept`. Use the platform's voice /
  echo-cancelling capture mode. The backend converts it to μ-law 8 kHz for the phone network.

### Backend → app (JSON)

```json
{"type": "risk", "score": 62, "level": "warn", "scamType": "grandchild", "reasons": ["money", "urgency"]}
```
After every risk assessment (roughly every 3–4 s while the caller speaks). `score` 0–100
(smoothed), `level` is `"none"`, `"warn"` or `"high"`, `scamType` is `"none"`,
`"grandchild"`, `"police"`, `"bank"` or `"other"`, `reasons` lists the warning signs found:
`"money"`, `"secrecy"`, `"authority"`, `"urgency"`. On the first `"warn"` the backend also
plays a short warning tone into the call channel audio.

```json
{"type": "verify_password"}
```
Risk is high. The app shows: "Ask the caller for the family password". The password can be
entered on the senior's keypad (`dtmf` below) or by the caller on their phone keypad. If the
correct password does not arrive within **20 s** (backend setting), or no family password is
configured, the backend blocks the call (`call_ended` with `scam_blocked`). A correct password
lets the call continue; there is no second check in the same call.

```json
{"type": "call_ended", "reason": "scam_blocked"}
```
`reason`: `"caller_hangup"`, `"senior_hangup"`, `"scam_blocked"`, `"timeout"` (not answered
within 30 s, or the maximum call length was reached) or `"error"`. The backend closes the
socket (1000) right after sending it. The app shows the result, e.g. for `scam_blocked`:
"We ended a suspicious call. Your trusted person has been informed."

### App → backend (JSON)

```json
{"type": "accept"}
```
The senior answers. Before `accept` the caller hears a ringback tone and no audio is bridged.
Without `accept` within **30 s** the call ends with `timeout`.

```json
{"type": "hangup"}
```
The senior ends the call, or rejects it while ringing. The backend answers with `call_ended`
(`senior_hangup`) and closes the socket.

```json
{"type": "dtmf", "digits": "1234"}
```
Keypad input (`0-9`, `*`, `#`, 1–32 characters) used for the family-password check while a
`verify_password` is pending. Ignored at other times.

If the call channel drops during a call, the backend ends the call (`error`). There is no
resume in v0.

## 3. Failure behaviour (fail-open for v0)

- **No app connected** (no open control channel) when a call arrives: the caller hears
  "protection temporarily unavailable" (PL/EN) and the call ends. The same happens when all
  call slots are busy. Planned later: forward the call to the senior's phone instead.
- App disconnects between the webhook and the media stream start: the call ends.
- The app shows "protection unavailable" whenever its control channel is not open.
- Speech-to-text or the decision model failing does not affect the call: audio keeps flowing,
  risk is scored by the keyword rules only, or not at all.

## 4. Example session

```
app → GET wss://host/app/control?device_token=…           (open)
be  → {"type":"protection_status","available":true}
app → {"type":"ping"}            be → {"type":"pong"}        (every 15 s)
      … a forwarded call arrives …
be  → {"type":"incoming_call","callId":"CA9f…","token":"pK3…","caller":"+48 *** *** 123","lang":"pl"}
app → GET wss://host/app/call/CA9f…?token=pK3…            (open)
app → {"type":"accept"}
be ⇄ app  binary audio frames (640 bytes, 20 ms)
be  → {"type":"risk","score":18,"level":"none","scamType":"none","reasons":["money"]}
be  → {"type":"risk","score":64,"level":"warn","scamType":"police","reasons":["authority","money"]}
be  → {"type":"risk","score":93,"level":"high","scamType":"police","reasons":["authority","money","secrecy"]}
be  → {"type":"verify_password"}
      … 20 s without the correct password …
be  → {"type":"call_ended","reason":"scam_blocked"}       (socket closed, 1000)
```

## 5. Security notes

- Tokens travel in the query string because WebSocket clients cannot set headers everywhere.
  The backend redacts `token` / `device_token` values from its access logs; always use `wss://`.
- The call token is short-lived and single use; the device token is long-lived and must be
  stored in the platform's secure storage (HarmonyOS Asset Store Kit, Android Keystore).
- No audio or transcript is stored by the backend; risk events carry categories and scores only.
