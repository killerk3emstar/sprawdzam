# AI features

> **Status: draft (4 Oct 2026, HackYeah).** Statements marked **[verified]** were measured by us on the
> development Mac (Apple M4 Pro, 48 GB RAM) with the scripts named next to them. **[designed]** means implemented
> in the backend (unit-tested, and run end to end with `server/scripts/smoke_call.py` against the real models)
> but not yet tested with real phone calls. **[planned]** means not built yet.

Sprawdzam / Second Ear protects older people from phone scams ("grandchild", fake police, fake bank employee,
investment fraud). Calls from numbers outside the senior's contacts are routed through our backend. Two
self-hosted models and a set of keyword rules estimate, while the call is going on, how likely it is to be a
scam. The system can warn the senior, ask the caller for the family password, end the call and alert a
trusted person.

What the AI does **not** do: no emotion recognition, no voice biometrics or speaker identification, no voice
cloning, no profiling of the caller. It analyses *what is said* (text), not *who* says it or *how they feel*.

## Models and components

| component | what it is | where it runs | role |
|---|---|---|---|
| **Whisper large-v3-turbo** (OpenAI, MIT licence) | speech-to-text, served by `whisper-server` from whisper.cpp 1.9.4 (Metal) | our machine (Mac / EC2), never a third-party API | turns utterances of call audio (caller 3–8 s, senior 1.5–8 s) into text; language forced from the senior's settings (PL or EN) |
| **basal-1.0-4.5B** (`Remek/basal-1.0-4.5B`, Apache 2.0, Polish decision model built on Bielik) | typed-decision model: answers yes/no, multiple-choice and ordinal-score questions about a text with calibrated probabilities | `basal-serve` on our machine, PyTorch MPS, bf16, with our `--share-state` patch | main scam-risk estimate (`risk`) and scam pattern (`scam_type`) |
| **basal-1.0-1.5B** (`Remek/basal-1.0-1.5B`, same API) | smaller variant | same server, other port | fallback if latency or GPU memory becomes a problem; evaluated, not the default |
| **Keyword rules** (ours, `server/app/risk/rules.py`) | 55 regular-expression rules (29 Polish, 26 English) in four categories (money, secrecy, authority, urgency) plus "story" context (accident, bail, account at risk, remote-access app) | backend process | safety net when the model is slow, down or wrong; combined with the model by taking the maximum |

Clef-Flash (`Cloudflare/clef-flash`) was considered as an alternative decision model and is **not used**: the
basal latency on the Mac turned out good enough after our patch, so we did not download it.

Our `--share-state` patch (`server/bench/basal/basal-share-state.patch`) makes basal-serve compute the shared
prompt prefix (system prompt + transcript) once for all questions of a request instead of once per question.
Answers stay equivalent (≤ 0.02 difference in probabilities, from bf16 batching) **[verified,
`server/bench/README.md`]**; latency for six questions dropped from 4.5 s to 1.9 s.

## Data flow

```
caller's phone audio (Twilio Media Stream, μ-law 8 kHz, 20 ms frames)
  → decode + resample to 16 kHz PCM                                     [designed]
  → pause-based segmentation into 3–8 s utterances (energy VAD)         [designed; Silero VAD planned]
senior's microphone (senior app, PCM16 16 kHz over the call WebSocket)
  → its own pause segmenter, 1.5–8 s utterances                         [designed]
  → one sequential Whisper worker for both sides, caller segments first;
    Whisper large-v3-turbo, language = senior's setting, 5 s timeout
    (3 s for senior segments; senior segments older than 12 s skipped)  [designed]
  → echo guard: drop a senior utterance that repeats the caller or our voice prompt
    from the last 15 s (the phone's speaker leaking into its microphone) [designed]
  → rolling transcript window, last 60 s, RAM only ("Dzwoniący: …" / "Senior: …")  [designed]
  → every new caller utterance (~3–4 s), and senior utterances when no caller one is waiting:
       basal-1: questions `risk` (low/medium/high/critical) + `scam_type`  [designed]
       keyword rules on the same window                                  [designed]
       score = max( 100·(1 − P(risk = low)), rules score )               [designed]
  → smoothing: warn when the last 2 combined readings are both ≥ 50;
               hang-up path only when the last 2 MODEL readings are both ≥ 90
               and (model secrecy ≥ 0.8 or a keyword-rule hit); rules alone never hang up  [designed]
  → actions (escalate only): spoken warning + in-app warning → ask the caller for the
    family password (DTMF) → end the call → the senior's phone texts the trusted person
    (`alert_trusted`, docs/APP_PROTOCOL.md)                               [designed]
  → alert summary (time, masked number, max score, scam type, outcome, actions; no transcript)
    in RAM for the operator console (`/dev/events`, `/dev/alerts`, last 50)  [designed]
```

- Two-tier questions: every reading asks only `risk` + `scam_type` (~1.1 s on the 4.5B model); after the first
  reading at or above the warning threshold, the full six-question schema (`money`, `secrecy`, `authority`,
  `urgency`, `scam_type`, `risk`, ~2 s) is asked once; its `secrecy` answer feeds the hang-up gate and the four
  signals become the `reasons` shown to the senior. **[designed, `server/app/risk/engine.py`]**
- The model score is `100·(1 − P(low))`, not the expected level: basal almost never picks `critical`, so the
  expected level of a clear scam stays around 63–65 and would never reach a hang-up threshold.
  **[verified, `server/bench/README.md`]**
- Question schema (PL and EN wording): `server/bench/basal/schema_pl.json`, `schema_en.json`. The transcript is
  passed as data; basal's system prompt tells the model that the state is data, not instructions.
- Both sides are transcribed: the caller from the phone stream and the senior from the app's microphone, labelled
  by speaker in the model's input. The senior's answers ("same account as always?", "I have 10 000 at home")
  are context the model needs (see the scenario evaluation below). Caller speech keeps priority on the shared
  Whisper server: in a live run with the senior's speaker looped back into the microphone (3 calls, 22 caller and
  30 senior segments) the caller's Whisper latency stayed at 0.94 s median with at most 0.74 s queueing, and all
  30 echo segments were dropped. **[designed; measured with `smoke_call.py --echo-gain 0.7` on synthetic TTS
  audio, not on a real phone]**

## Privacy and data protection

- **No recording.** Audio and transcripts exist only in process memory for the duration of the call and are
  discarded when it ends. They are never written to disk, never logged and never sent to a third-party AI
  service. **[designed; backend logs carry call ids, scores, categories and error types only]**
- **What is stored**: a short alert summary per analysed call (time, masked number, max risk score, scam type,
  outcome, which actions ran), in memory only (last 50), for the operator console. No transcript text. Phone
  numbers are masked in logs and on the console. **[designed]** The live console stream shows transcript lines
  while a call is running; they are not stored or logged.
- **Transparency to the caller**: before the call is connected the caller hears that the call is protected and
  checked for fraud in real time and is not recorded (`server/app/prompts.py`, PL and EN).
- **EU AI Act**: we do not infer emotions from voice (emotion recognition is prohibited in workplaces and
  education and high-risk elsewhere) and do not use biometric identification. The decision models only see text.
- **Data minimisation**: the decision model sees a 60 s window, not the whole call. Calls from the senior's
  contacts are not analysed: the app sends its whitelist in `settings`, and the backend bridges those calls
  without the protection notice, speech-to-text or risk analysis. **[designed, `server/app/relay/`]**
- Self-hosting: Whisper and basal run on hardware we control (Mac during the hackathon, one EC2 instance for the
  deployment), so call content does not leave our infrastructure.

## Validation

### 1. Model bench (latency and smoke test) — `server/bench/README.md` [verified]

- Whisper large-v3-turbo on simulated phone audio (TTS → 300–3400 Hz, 8 kHz μ-law): ~0.5 s per 2–4 s chunk,
  WER 0.06–0.23 on whole Polish clips, 0.07–0.18 on 4 s chunks.
- basal-1.0-4.5B, MPS + share-state: `risk` + `scam_type` 1.07 s p50 per reading, peak memory 10.3 GB;
  1.5B: 0.39 s, 4.9 GB.
- 14 hand-written transcripts: scam type 14/14; `risk_not_low` 64–99 for scams and 0–5 for normal calls.

### 2. Scenario evaluation — `server/bench/eval/RESULTS.md` [verified]

300 synthetic call transcripts (`scenarios/`, 180 PL / 120 EN, 150 scams / 150 normal calls, 115 of the normal
calls are hard negatives such as a grandson really borrowing money or a real bank calling about a card).
Each system reads the whole transcript once; warn ≥ 50, hang-up ≥ 90.

| system | precision (warn) | recall (warn) | false-positive rate (warn) | recall (hang-up) | FPR (hang-up) | scam type correct | latency p50 |
|---|---|---|---|---|---|---|---|
| keyword rules only | 0.92 | 0.61 | 0.05 | 0.41 | 0.02 | 43% | 0.1 ms |
| basal-1.0-4.5B only | 0.97 | 0.97 | 0.03 | 0.89 | 0.01 | 93% | 1.09 s |
| basal-1.0-1.5B only | 0.98 | 0.90 | 0.02 | 0.40 | 0.01 | 76% | 0.36 s |
| **max(basal-4.5B, rules)** (what the backend does) | 0.93 | **1.00** | 0.07 | 0.94 | 0.02 | 93% | ≈ 1.1 s |

Since 4 Oct the backend warns on max(model, rules) but lets only the model's own score reach the hang-up path
(see below), so for hang-up the "basal-1.0-4.5B only" row (recall 0.89, FPR 0.01) is the closer estimate; the
evaluation was not re-run for this change.

Findings that shaped the design:

- The model is the backbone (ROC AUC 0.99); the rules alone miss 39% of scams but rescue the few scams the model
  under-scores (mostly English fake-police calls), so the combination catches 150/150 scams in this set.
- **Context from the senior matters**: if only the caller's turns are analysed, the false-warning rate rises
  from 7% to 26% (a relative asking to borrow money looks like a scam without the senior's "same account as
  always?"). These numbers are from the offline evaluation on synthetic transcripts. **[verified on synthetic
  data]** The backend now transcribes the senior's side too **[designed]**; the live effect on false warnings has
  not been measured.
- Regex rules cannot read negation ("the bank never asks for BLIK codes" scores 90), so rules alone may warn but
  never hang up: the hang-up path needs the model's own score ≥ 90 twice in a row. With the model down the
  engine reaches at most a warning. **[designed, unit-tested in `server/tests/test_engine.py`]**
- The 1.5B model is a fallback only: its scores are compressed (hang-up recall 0.40 at the same threshold).

Turn-by-turn replay (64-call subset, the model reads the transcript after every turn, server smoothing): every
scam got a warning, at a median of ~12 s of speech (p90 40 s), and 29/32 reached the hang-up path (median 22 s);
4 of 32 normal calls got a false warning mid-call (a neighbour or a courier mentioning money, before the context
made it harmless) and none was hung up on. With caller-only transcripts, 1 of 32 normal calls (a courier collecting
cash on delivery) would have been hung up on. **[verified on synthetic data]**

Details, per-family results, failure examples by id and the exact commands: `server/bench/eval/RESULTS.md`.

## Limitations

- **Synthetic evaluation data.** The scenarios were written by an AI model (Claude) from templates and
  hand-written seeds; real scammers improvise and real Whisper output on phone audio is messier. The numbers
  above are an optimistic estimate, not a field result.
- **TTS audio, not real calls.** The speech-to-text bench used macOS text-to-speech through a simulated phone
  line; we have not measured Whisper on real phone calls with background noise and elderly voices.
- **Senior's speech and echo.** The senior's side is transcribed from the app's microphone; the echo guard is
  text-based (similarity to what the speaker just played), so a senior who repeats the caller word for word
  ("30 thousand in cash?") within 15 s is dropped as echo. Senior speech that overlaps long caller monologues
  waits for the caller and is skipped after 12 s.
- **Demo setup.** The demo runs on a physical Android phone with a browser page playing the caller (no real
  telephony; Twilio in dry-run). Audio routing and echo on other phones may differ.
- **Short windows.** The model sees the last 60 s; a slow scam that sets up trust over several minutes is only
  judged on its latest part.
- **Thresholds were not tuned on held-out data.** The evaluation and any threshold proposal use the same 300
  calls.
- **Adversarial callers.** A caller can say things meant to manipulate the model ("this is not a scam"); the
  rules and the max() combination limit the damage, but this was not tested systematically.
- **Language**: Polish and English only; the language is forced from the senior's settings, so a call in another
  language is transcribed badly and judged mostly by the rules.

## Failure behaviour

| failure | behaviour | status |
|---|---|---|
| basal timeout (2–3 s), HTTP error, malformed or out-of-range answer | logged as `decision_fallback_to_rules`; that reading uses the rules only | designed (`server/app/risk/engine.py`, unit-tested on the server branch) |
| Whisper error or timeout | logged (`stt_failed`), audio keeps flowing, session marked degraded; no new text, so no new escalation | designed |
| Whisper slower than real time | per-speaker queues of 4 segments, oldest dropped (`stt_backlog_drop`); caller first; stale senior segments skipped | designed |
| one reading spikes (misheard word, model hiccup) | at most a warning; hang-up needs two consecutive model readings ≥ 90 | designed (`smoothing.py`) |
| decision model down for the whole call | keyword rules only: the senior can be warned, but the call is never ended automatically | designed (`engine.py`) |
| senior app not connected / all call slots busy | **fail-open**: "protection temporarily unavailable, connecting without protection" and Twilio `<Dial>` to `SENIOR_NUMBER`; without that route (unset or dry-run) a neutral notice and the call ends; `fail_open` event on the console; app shows "protection unavailable" | designed (dial path not tested with a real call) |
| backend down entirely | Twilio fallback URL dials the senior directly (**fail-open**: calls still go through, unprotected) | planned (provider configuration) |
| outbound alert actions | dry-run by default, allowlist, daily caps, one alert per incident | designed (`server/app/telephony/guard.py`) |

## Reproducing

```bash
uv run scenarios/generator/generate.py --stats                      # rebuild the dataset (deterministic)
server/bench/run-basal.sh                                           # basal-1.0-4.5B on :8000
BASAL_MODEL=~/models/sprawdzam/basal-1.0-1.5B BASAL_PORT=8001 server/bench/run-basal.sh
uv run server/bench/eval/run_eval.py collect --url http://127.0.0.1:8000 --name basal-4.5B
uv run server/bench/eval/run_eval.py collect --url http://127.0.0.1:8001 --name basal-1.5B
uv run server/bench/eval/run_eval.py progressive --url http://127.0.0.1:8000 --name basal-4.5B --subset 64
uv run server/bench/eval/run_eval.py report
```
