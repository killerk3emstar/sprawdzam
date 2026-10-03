# AI features

> **Status: draft (3 Oct 2026, HackYeah).** Statements marked **[verified]** were measured by us on the
> development Mac (Apple M4 Pro, 48 GB RAM) with the scripts named next to them. **[designed]** means implemented
> in the backend but not yet tested end to end with real phone calls. **[planned]** means not built yet.

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
| **Whisper large-v3-turbo** (OpenAI, MIT licence) | speech-to-text, served by `whisper-server` from whisper.cpp 1.9.4 (Metal) | our machine (Mac / EC2), never a third-party API | turns 3–8 s utterances of call audio into text; language forced from the senior's settings (PL or EN) |
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
  → Whisper large-v3-turbo, language = senior's setting, 3 s timeout    [client planned]
  → rolling transcript window, last 60 s, RAM only ("caller: …")        [designed]
  → every new utterance (~3–4 s):
       basal-1: questions `risk` (low/medium/high/critical) + `scam_type`  [client planned]
       keyword rules on the same window                                  [designed]
       score = max( 100·(1 − P(risk = low)), rules score )               [designed]
  → smoothing: warn when the mean of the last 2 readings ≥ 50;
               hang-up path when the last 2 readings are both ≥ 90        [designed]
  → actions (escalate only): warning tone + in-app warning → ask the caller for the
    family password (DTMF) → end the call → call/SMS the trusted person  [designed]
  → alert summary (time, score, scam type, which signals fired) for the family panel  [planned]
```

- Two-tier questions: every reading asks only `risk` + `scam_type` (~1.1 s on the 4.5B model); when the warning
  threshold is crossed, the full six-question schema (`money`, `secrecy`, `authority`, `urgency`, `scam_type`,
  `risk`, ~2 s) can be asked once to build the alert summary. **[designed in the bench, not wired]**
- The model score is `100·(1 − P(low))`, not the expected level: basal almost never picks `critical`, so the
  expected level of a clear scam stays around 63–65 and would never reach a hang-up threshold.
  **[verified, `server/bench/README.md`]**
- Question schema (PL and EN wording): `server/bench/basal/schema_pl.json`, `schema_en.json`. The transcript is
  passed as data; basal's system prompt tells the model that the state is data, not instructions.
- Today the backend transcribes **only the caller's side** (the inbound phone track). The senior's speech is
  relayed to the caller but not analysed. **[designed]**

## Privacy and data protection

- **No recording.** Audio and transcripts exist only in process memory for the duration of the call and are
  discarded when it ends. They are never written to disk, never logged and never sent to a third-party AI
  service. **[designed; backend logs carry call ids, scores, categories and error types only]**
- **What is stored**: a short alert summary per suspicious call (time, risk score, scam type, which warning
  signs fired, which actions ran) for the family panel. **[planned]** Phone numbers are masked in logs.
- **Transparency to the caller**: before the call is connected the caller hears that the call is protected and
  checked for fraud in real time and is not recorded (`server/app/prompts.py`, PL and EN).
- **EU AI Act**: we do not infer emotions from voice (emotion recognition is prohibited in workplaces and
  education and high-risk elsewhere) and do not use biometric identification. The decision models only see text.
- **Data minimisation**: the decision model sees a 60 s window, not the whole call. Calls from the senior's
  contacts are not analysed: on Android they ring normally (call screening), on HarmonyOS, where apps cannot
  reject calls, they are forwarded and passed straight through by a cloud allowlist. **[planned]**
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

Findings that shaped the design:

- The model is the backbone (ROC AUC 0.99); the rules alone miss 39% of scams but rescue the few scams the model
  under-scores (mostly English fake-police calls), so the combination catches 150/150 scams in this set.
- **Context from the senior matters**: if only the caller's turns are analysed (the current backend), the
  false-warning rate rises from 7% to 26% (a relative asking to borrow money looks like a scam without the
  senior's "same account as always?"). Transcribing the senior's side is the next precision improvement. **[verified
  on synthetic data; not yet implemented]**
- Regex rules cannot read negation ("the bank never asks for BLIK codes" scores 90), so we recommend that rules
  alone may warn but not hang up. **[recommendation, not yet implemented]**
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
- **Only the caller's voice is analysed.** The senior's answers ("I have 10 000 at home") are not transcribed
  today, which removes context the model could use.
- **Emulator.** The senior app is demonstrated on the HarmonyOS emulator; audio routing on a real phone may
  differ.
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
| one reading spikes (misheard word, model hiccup) | at most a warning; hang-up needs two consecutive readings ≥ 90 | designed (`smoothing.py`) |
| senior app not connected / all call slots busy | caller hears "protection temporarily unavailable"; app shows "protection unavailable" | designed (v0; forwarding the call to the senior's phone instead is planned) |
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
