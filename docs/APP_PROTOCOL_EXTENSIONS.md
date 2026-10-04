# App protocol extensions proposed by the app (pending backend agreement)

The base protocol is `docs/APP_PROTOCOL.md` in the server repository (v0, branch `feat/server-skeleton`).
Messages below are sent by the app today; the v0 backend ignores unknown types, so they are safe to send
before the backend implements them. Changes must be agreed by both sides.

## `settings` (app → backend, control channel)

```json
{"type": "settings", "lang": "pl", "trustedPerson": {"name": "Anna", "number": "+48600100200"}, "whitelist": ["+48600100200", "+48501234567"]}
```

- Sent right after every control-channel (re)connect and whenever the senior changes settings.
- `lang`: `"pl"` or `"en"`, the senior's language for voice prompts, speech-to-text and alerts.
- `trustedPerson`: `{"name", "number"}` picked with the system contact picker, or `null` when not chosen.
  The backend calls/texts this number on high risk.
- `whitelist`: numbers whose calls should ring normally without analysis (the senior chooses the contacts
  in the system picker, multi-select). Normalized to E.164-like form: digits with a leading `+`; `00` → `+`;
  9-digit numbers are treated as Polish (`+48`).
- Personal data: the whitelist and the trusted person are sent only over the control channel (`wss://` in
  production) and are never logged by the app (only counts). The backend should keep them in memory or
  encrypted, and must not log them either.
- The latest message replaces the previous settings completely (no merging).

Why the picker: on HarmonyOS `ohos.permission.READ_CONTACTS` is a `system_basic` (ACL-restricted) permission.
The contact picker (`contact.selectContacts`) needs no permission and only returns the contacts the user
selects.

## `alert_trusted` / `alert_trusted_result` (control channel, Android app)

The senior's own phone texts the trusted person, so the SMS comes from a number the family knows and no SMS
provider is needed.

Backend → app:

```json
{"type": "alert_trusted", "callId": "CA…", "scamType": "police", "reasons": ["authority", "money"], "lang": "pl",
 "text": "Sprawdzam: babcia mogla rozmawiac z oszustem (falszywy policjant, prosba o gotowke). Zadzwon do niej."}
```

App → backend:

```json
{"type": "alert_trusted_result", "callId": "CA…", "sent": true}
{"type": "alert_trusted_result", "callId": "CA…", "sent": false, "error": "no_permission"}
```

- `text` is sent as is (the backend writes it in `lang`; plain ASCII keeps it to one 160-character GSM-7 SMS;
  longer texts are split with `SmsManager.divideMessage` and sent as a multipart SMS).
- The recipient is the trusted person from the app settings (the `trustedPerson.number` also sent in
  `settings`); the backend does not send a number.
- `sent: true` only after the radio confirmed every part (sent `PendingIntent` with `RESULT_OK`); no
  confirmation within 60 s counts as `send_failed`.
- `error`: `no_permission` (SEND_SMS not granted), `no_number` (no trusted person chosen), `send_failed`
  (radio error, no SIM/service, timeout).
- One SMS per `callId`: the app ignores repeated `alert_trusted` for the same call (no second result).
- The message may arrive during the call, after `call_ended`, or while the app is in the background (the
  control channel is kept alive by a foreground service). If the control channel is down when the result is
  ready, the app queues it and sends it after reconnecting.
- The app shows the result on the call-ended screen ("Wysłano SMS do: Anna ✓" or the error).
- Permission: SEND_SMS is requested when the senior chooses the trusted person and at app start if a trusted
  person is set; never during a call.
- Privacy: the app never logs the number or the text, only the result.

HarmonyOS: not implemented (the HarmonyOS app is frozen; third-party apps cannot send SMS silently there).

## Family-password countdown and blocking without a password (call channel)

### `verify_password.timeoutSeconds` (backend → app)

```json
{"type": "verify_password", "timeoutSeconds": 12}
```

- `timeoutSeconds` (new, optional): how long the backend waits for the correct family password before it ends
  the call with `call_ended` `scam_blocked`. The app shows a live countdown on the keypad screen
  ("Zostało 9 s" / "9 s left"); at zero it shows "Czas minął. Rozłączamy." and waits for `call_ended`.
- Absent (older backends; the frozen HarmonyOS module does not forward it): the app assumes **12 s**.
  Values outside 1–120 are treated as absent (120 is the cap).

### `confirm_block` (backend → app, new)

```json
{"type": "confirm_block", "seconds": 8}
```

- Sent instead of `verify_password` when risk is high and **no family password is configured**.
- The app switches to a full-screen red warning: "To wygląda na oszustwo. Rozłączam za 8 s" with a live
  countdown and one large "Rozłącz teraz" (Hang up now) button that sends `{"type": "hangup"}`.
  There is deliberately **no "continue" option**.
- The backend ends the call after `seconds` with `call_ended` `scam_blocked` (and the trusted-person alert).
  If no `call_ended` arrived 3 s after the countdown reached zero, the app sends `hangup` itself.
- `seconds` absent or invalid: 8.
- Only the first `confirm_block` per call counts (a repeat does not restart the countdown).

### `hangup` during a high-risk call (app → backend, changed semantics)

The senior's `{"type": "hangup"}` after the call reached high risk (and no correct family password was given)
now ends the call with `call_ended` `scam_blocked` instead of `senior_hangup`, so the trusted-person SMS goes
out. The app shows the blocked-call result screen. If the senior hangs up from the `confirm_block` screen and the
backend's answer does not arrive within the app's 2 s hang-up grace period (the app then ends the call locally as
`senior_hangup`), the app still shows the blocked-call result.

### Blocked-call result screen (app only)

After `scam_blocked`: "Rozłączyliśmy podejrzaną rozmowę", the SMS result line (`alert_trusted_result`), the advice
"Nie oddzwaniaj na ten numer. Nie podawaj pieniędzy ani kodów.", and, when a trusted person is set, a large
"Zadzwoń do: {name}" button that opens the phone's dialer with the trusted person's number filled in (`tel:`
URI, `ACTION_VIEW` → dialer; no `CALL_PHONE` permission, the senior presses call). This follows the police's
advice: hang up, then call the relative back on a number you know.

Native events (Android `CallEngine` module): `CallEngine.onVerifyPassword` now carries `timeoutSeconds`;
new `CallEngine.onConfirmBlock` `{callId, seconds}`. The TurboModule spec is unchanged. HarmonyOS: not
implemented (frozen); the shared JS falls back to the 12 s default and never receives `confirm_block`.
