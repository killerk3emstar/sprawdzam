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
