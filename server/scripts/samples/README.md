# Caller scripts for the demo

Caller-side monologues (the scammer, or a family member in the normal calls). The senior's side
is spoken live by whoever holds the senior's phone. All texts are our own material.

| File | Language | Pattern | Voice (`say`) | What it must show |
| --- | --- | --- | --- | --- |
| `pl_scam_police.txt` | PL | fake police officer | Zosia | authority, urgency, secrecy ("nie mówić nikomu, nawet rodzinie"), cash handover or transfer |
| `pl_scam_grandchild.txt` | PL | grandchild in trouble | Zosia | accident, bail in cash now, secrecy ("nie mów nikomu") |
| `pl_normal_grandchild.txt` | PL | normal call | Zosia | money mentioned in a benign way (birthday gift, paying back a loan): no alarm |
| `en_scam_police.txt` | EN | fake police officer | Daniel | same as the PL police script |
| `en_scam_grandchild.txt` | EN | grandchild in trouble | Samantha | same as the PL grandchild script |
| `en_normal_grandchild.txt` | EN | normal call | Samantha | same as the PL normal call |

Older clips kept for the model bench and as extras in `/dev/caller` ("more scripts"):
`pl_scam_bank`, `en_scam_bank`, `pl_normal_family`, `en_normal_family`.

## Rendering

```bash
cd server
scripts/make_samples.sh                      # all *.txt -> data/samples/<name>.ulaw
scripts/make_samples.sh --only pl_scam_police
```

Output: raw G.711 mu-law, 8 kHz, mono, phone band-pass (300-3400 Hz), which `/dev/caller`
streams as is. A 700 ms silence is inserted between sentences, so the backend's pause-based
segmenter cuts 3-8 s segments as it would for a real caller. The audio is not committed (Apple
voice licensing); render it on each machine. Needs macOS `say` and `ffmpeg`.

## Results against the models

Each clip was streamed through the backend in real time with `scripts/smoke_call.py` (caller in
Twilio Media Streams format, senior app accepting the call and saying nothing), 15 s of silence
after the clip:

```bash
set -a; source .env.dev; set +a
uv run python scripts/smoke_call.py --base http://127.0.0.1:8767 \
    --audio data/samples/pl_scam_police.ulaw --lang pl --tail-seconds 15
```

Setup: 4 Oct 2026, ~04:00, M4 Pro, whisper large-v3-turbo (whisper-server, Metal),
basal-1.0-4.5B (`--mode mps --share-state`), backend from branch `feat/demo-web` (based on
`main` at `eeec188`): warn at 50, family password question at 90 twice, then a hang-up when
nobody types the password. Times are seconds from the start of the media stream; the clip
starts when the senior answers, about 0.5 s later.

| Script | Clip | Max score | First warn | Password prompt | Outcome | Scam type | Reasons at peak |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `pl_scam_police` | 53 s | 100 | – | 21 s | `scam_blocked` at 42 s | police | money, secrecy, authority, urgency |
| `pl_scam_grandchild` | 50 s | 100 | 18 s | 26 s | `scam_blocked` at 47 s | grandchild | money, secrecy, authority, urgency |
| `pl_normal_grandchild` | 45 s | 23 | – | – | no alert (clip ended, caller hung up) | none | money |
| `en_scam_police` | 51 s | 100 | 19 s | 28 s | `scam_blocked` at 48 s | police | money, secrecy, authority, urgency |
| `en_scam_grandchild` | 43 s | 100 | 22 s | 30 s | `scam_blocked` at 50 s | grandchild | money, secrecy, authority, urgency |
| `en_normal_grandchild` | 39 s | 23 | – | – | no alert (clip ended, caller hung up) | none | money |

Reading the table:

* All four scams reach the family password question in 21-30 s, while the scammer is still
  talking. `secrecy` first appears at 21 s (PL police), 19 s (EN police), 37 s (PL grandchild)
  and 30 s (EN grandchild); the grandchild scripts also contain rule phrases ("nie mów
  nikomu", "don't tell anyone"). In
  `pl_scam_police` the score jumps from 61 (one reading, not yet a warning) straight to 98, so
  the warning step is skipped. The hang-up (`scam_blocked`) comes about 20 s after the password
  question, because the smoke test never types the password.
* Both normal calls stay at 23 at most (the model sees money, but no other warning sign), well
  below the warning threshold of 50.
* Tuning: the backend is moving to "hang up only with secrecy >= 0.8 or a rule hit", so the
  secrecy sentence comes early in every scam script. In the first versions it came late and
  `secrecy` only showed up at 44-48 s in the police scripts; "to musi zostać tylko między nami"
  in the PL grandchild script was never reported as `secrecy`, "To ma być tajemnica, nie mów
  nikomu" is.
* Re-run the six clips after backend changes to the thresholds or the hang-up rule.
