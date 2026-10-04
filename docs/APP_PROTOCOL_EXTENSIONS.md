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
