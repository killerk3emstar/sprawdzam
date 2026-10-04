# Risk engine evaluation: rules vs basal-1 vs the production combination

Run on 3 Oct 2026 on the development Mac (Apple M4 Pro, 48 GB RAM), basal-serve in mode `mps` with our
`--share-state` patch. Dataset: `scenarios/calls.jsonl`, **300 synthetic transcripts** (180 PL / 120 EN; 150
scams / 150 normal calls, of which 115 are hard negatives). Script: `run_eval.py`. Full generated tables:
`results/tables.md`; raw model answers: `results/raw_*.jsonl`, `results/progressive_*.jsonl`; per call:
`results/per_call.csv`; all metrics: `results/summary.json`.

> **Read this first.** The data is synthetic and was written by an AI model (see `scenarios/README.md`).
> The basal model and the scenario author have probably seen the same public descriptions of these scams, so
> the numbers below are an optimistic estimate of what to expect on real calls. Thresholds were not tuned on
> held-out data. Use the results to compare systems and to find failure modes, not as a promise of field
> accuracy.

## TL;DR

Whole transcript, one reading per call, both speakers in the transcript (`full` view):

| system | warn ≥ 50: precision | recall | F1 | FPR | hang-up ≥ 90: recall | FPR | ROC AUC | scam_type acc. (scams) | latency p50 / p95 |
|---|---|---|---|---|---|---|---|---|---|
| keyword rules | 0.92 | 0.61 | 0.74 | 0.05 | 0.41 | 0.02 | 0.91 | 0.43 | 0.1 ms |
| basal-1.0-4.5B | 0.97 | 0.97 | 0.97 | 0.03 | 0.89 | 0.01 | 0.99 | 0.93 | 1.09 s / 2.11 s |
| basal-1.0-1.5B | 0.98 | 0.90 | 0.94 | 0.02 | 0.40 | 0.01 | 0.98 | 0.76 | 0.36 s / 0.45 s |
| **max(4.5B, rules)** (production) | 0.93 | **1.00** | 0.96 | 0.07 | 0.94 | 0.02 | 0.99 | 0.93 | ≈ 4.5B |
| max(1.5B, rules) | 0.94 | 0.94 | 0.94 | 0.06 | 0.63 | 0.02 | 0.98 | 0.76 | ≈ 1.5B |

The same, but **only the caller's turns** in the transcript (`caller` view = what the backend transcribes today):

| system | warn ≥ 50: precision | recall | FPR | hang-up ≥ 90: recall | FPR | false hang-ups |
|---|---|---|---|---|---|---|
| keyword rules | 0.93 | 0.61 | 0.05 | 0.40 | 0.01 | 2 |
| basal-1.0-4.5B | 0.80 | 1.00 | **0.25** | 0.91 | 0.05 | 8 |
| max(4.5B, rules) | 0.79 | 1.00 | **0.26** | 0.95 | 0.05 | 8 |

1. **basal-4.5B is the backbone**: it catches 97% of scams at a 3% false-positive rate and separates the classes
   almost perfectly (AUC 0.99). The rules alone catch only 61%.
2. **The combination works as intended**: rules rescue the 5 scams basal-4.5B under-scores (4 English fake
   police/sheriff calls, 1 English grandchild call), giving 150/150 caught, at the cost of 6 extra false warnings from the rules.
3. **The senior's side of the conversation matters a lot.** With caller-only transcripts the false-warning rate
   rises from 7% to 26% and false hang-ups from 3 to 8: a son asking to borrow 500 zł looks like a scam when the
   model does not hear "same account as always? does mum know?". **Transcribing the senior's side is the single
   most valuable improvement for precision.**
4. **basal-1.5B is not a drop-in replacement**: similar warn performance but its scores are compressed (hang-up
   recall 0.40 vs 0.89) and it misses 6 of 16 Polish fake-bank calls. Keep it only as an emergency fallback with
   its own lower hang-up threshold.
5. **Turn by turn** (64-call subset, server smoothing): every scam is warned at a median of ~12 s of speech and
   29/32 reach the hang-up path (median 22 s); 4/32 normal calls get a mid-call false warning and none is hung up
   on (1/32 in the caller-only view).

## Setup

| system | score 0–100 | scam type |
|---|---|---|
| rules | `RulesResult.score` of `rules_snapshot.py`, a copy of `server/app/risk/rules.py` (branch `feat/server-skeleton`, commit `bfffe0d`) on the plain text of the window | `RulesResult.scam_type` |
| basal-4.5B / 1.5B | `100·(1 − P(risk = low))`, question `risk` of `../basal/schema_{pl,en}.json` | `scam_type` choice (no `investment` option, so `investment` → `other`) |
| max(model, rules) | `max(model, rules)`, as `combine_scores()` in `server/app/risk/engine.py` | model's type unless `none`, else the rules' |

- One request per reading with the questions `risk` + `scam_type` (the first tier of the two-tier design);
  state = `TranscriptWindow.render()` format (`caller: …\nsenior: …`), PL questions for PL calls, EN for EN.
- Thresholds from the server config: warn ≥ 50 (`RISK_WARN`), hang-up ≥ 90 (`RISK_HANGUP`). For the
  whole-transcript runs one reading is the decision (no smoothing).
- A call is ≤ 142 words (~60 s of speech), so the whole transcript ≈ the backend's 60 s rolling window.
- Latency is measured on the client (HTTP round trip) with nothing else running on the GPU except other
  clients of the shared 4.5B server (we cannot rule out occasional requests from the team's backend tests).
- All 900 whole-transcript model requests and all 1,742 turn-by-turn readings succeeded (0 HTTP errors, 0 malformed answers).

## Whole transcript, both speakers (`full`)

Breakdown at warn ≥ 50, recall on scams / false-positive rate on normal calls:

| system | PL | EN | easy | hard | hand-written (n = 28) |
|---|---|---|---|---|---|
| rules | 0.58 / 0.07 | 0.67 / 0.03 | 0.69 / 0.00 | 0.53 / 0.07 | 0.21 / 0.29 |
| basal-4.5B | 1.00 / 0.03 | 0.92 / 0.03 | 0.97 / 0.00 | 0.96 / 0.04 | 1.00 / 0.21 |
| basal-1.5B | 0.88 / 0.01 | 0.93 / 0.03 | 0.96 / 0.00 | 0.84 / 0.03 | 0.57 / 0.21 |
| max(4.5B, rules) | 1.00 / 0.09 | 1.00 / 0.05 | 1.00 / 0.00 | 1.00 / 0.10 | 1.00 / 0.36 |

Threshold sweep (recall / FPR):

| system | ≥ 30 | ≥ 40 | ≥ 50 | ≥ 60 | ≥ 70 | ≥ 80 | ≥ 90 | ≥ 95 |
|---|---|---|---|---|---|---|---|---|
| rules | 0.73 / 0.11 | 0.65 / 0.07 | 0.61 / 0.05 | 0.53 / 0.05 | 0.52 / 0.05 | 0.45 / 0.03 | 0.41 / 0.02 | 0.39 / 0.01 |
| basal-4.5B | 1.00 / 0.13 | 0.99 / 0.07 | 0.97 / 0.03 | 0.95 / 0.02 | 0.94 / 0.02 | 0.91 / 0.01 | 0.89 / 0.01 | 0.80 / 0.01 |
| basal-1.5B | 0.93 / 0.07 | 0.93 / 0.03 | 0.90 / 0.02 | 0.83 / 0.01 | 0.70 / 0.01 | 0.55 / 0.01 | 0.40 / 0.01 | 0.23 / 0.01 |
| max(4.5B, rules) | 1.00 / 0.21 | 1.00 / 0.13 | 1.00 / 0.07 | 0.99 / 0.06 | 0.98 / 0.05 | 0.95 / 0.03 | 0.94 / 0.02 | 0.89 / 0.01 |

Confusion matrices (TP/FP/FN/TN), warn ≥ 50: rules 92/8/58/142, basal-4.5B 145/5/5/145, basal-1.5B
135/3/15/147, max(4.5B, rules) 150/11/0/139, max(1.5B, rules) 141/9/9/141. Hang-up ≥ 90: rules 61/3/89/147,
basal-4.5B 133/1/17/149, max(4.5B, rules) 141/3/9/147.

Exploratory action policies for basal-4.5B + rules (same data, so only indicative):

| policy | precision | recall | FPR | TP/FP/FN/TN |
|---|---|---|---|---|
| warn: max ≥ 50 (production) | 0.93 | 1.00 | 0.07 | 150/11/0/139 |
| warn: model ≥ 50 or rules ≥ 80 | 0.96 | 0.99 | 0.05 | 149/7/1/143 |
| hang-up: max ≥ 90 (production) | 0.98 | 0.94 | 0.02 | 141/3/9/147 |
| hang-up: model ≥ 90 (rules can only warn) | 0.99 | 0.89 | 0.01 | 133/1/17/149 |
| hang-up: max ≥ 90 and model ≥ 50 | 0.99 | 0.91 | 0.01 | 137/2/13/148 |
| hang-up: max ≥ 90 and any rule category hit (server's planned guard) | 0.98 | 0.86 | 0.02 | 129/3/21/147 |

Scam type (basal-4.5B, rows = truth): grandchild 45/45, police 30/34 (3 → bank, 1 → grandchild), bank 30/31,
other + investment 35/40. On normal calls it says `none` 136/150 (11 → grandchild, mostly family calls about money; 3 → police).
The rules get the type right for only 43% of scams, mostly because they return `none` below score 30.

## Caller turns only (`caller`)

| family (normal calls) | n | basal-4.5B false warnings, full view | caller view |
|---|---|---|---|
| family_money (PL+EN) | 19 | 0 | 12 |
| neighbour_borrow (PL+EN) | 9 | 0 | 8 |
| grandchild_secret (PL+EN) | 10 | 1 | 4 |
| courier_real | 7 | 1 | 4 |
| handwritten normal calls | 14 | 3 | 4 |
| bank_real (PL+EN) | 15 | 0 | 2 |
| surprise_party (PL+EN) | 9 | 0 | 2 |
| sales_legit | 2 | 0 | 1 |
| all other normal families | 65 | 0 | 0 |
| **total** | 150 | 5 | 37 |

Scam recall stays at 100%; the loss is entirely precision. Without the senior's turns the model sees a caller who
asks for money (or a secret) and nothing that makes it plausible. Polish calls suffer most (FPR 0.36 vs 0.08 for
English) because the Polish templates carry more of the reassurance in the senior's lines. Latency is lower
(p50 0.90 s) because the state is shorter.

## Turn by turn

Replay of a stratified subset: 64 calls = 8 per language × label × difficulty (32 scams; 32 normal calls, of
which 16 plain chats and 16 hard negatives: police_real 3, medical 3, neighbour_borrow 2, bank_real 2, hand-written
2, surprise_party, family_money, grandchild_secret, courier_real 1 each). After every turn the model reads all
turns so far (question `risk` only), like the backend after each new utterance. Time ≈ words so far / 2.5 words
per second. Smoothing: `single` = act on one reading; `avg2` = the server's `ScoreSmoother` (warn when the mean of
the last 2 readings ≥ 50, hang-up when the last 2 readings are both ≥ 90); `2row` = warn only after 2 consecutive
readings ≥ 50 (hang-up as in `avg2`).

`full` view (both speakers), 673 readings:

| system | smoothing | scams warned | median time to warn | p90 | share of call elapsed (median) | scams hung up | median time to hang-up | normal calls falsely warned | falsely hung up |
|---|---|---|---|---|---|---|---|---|---|
| rules | avg2 | 21/32 | 28 s | 46 s | 0.83 | 8/32 | 32 s | 0/32 | 0/32 |
| basal-4.5B | avg2 | 31/32 | 12 s | 36 s | 0.38 | 28/32 | 22 s | 4/32 | 0/32 |
| **max(4.5B, rules)** | single | 32/32 | 10 s | 34 s | 0.33 | 32/32 | 21 s | 4/32 | **1/32** |
| **max(4.5B, rules)** | **avg2 (server)** | **32/32** | **12 s** | 40 s | 0.41 | 29/32 | 22 s | **4/32** | **0/32** |
| max(4.5B, rules) | 2row | 32/32 | 19 s | 40 s | 0.55 | 29/32 | 22 s | 3/32 | 0/32 |
| max(1.5B, rules) | avg2 | 32/32 | 13 s | 40 s | 0.41 | 19/32 | 21 s | 2/32 | 0/32 |

`caller` view (only the caller's turns), 4.5B, 396 readings: max(4.5B, rules) with `avg2` warns 32/32 scams
(median 13 s), hangs up 31/32, falsely warns 5/32 normal calls and **falsely hangs up 1/32**
(`pl_courier_real_07`, cash on delivery: readings 93, 90). Risk-only latency in the replays: 4.5B p50 0.94 s / p95 1.98 s,
1.5B 0.36 s / 0.48 s (measured while other replays shared the GPU).

- **Early enough.** With the server smoothing, every scam in the subset triggers a warning, at a median of ~12 s
  of speech (about 40% into the call), and 29/32 reach the hang-up path (median 22 s). The rules alone warn
  later (28 s) and miss a third.
- **Partial transcripts are harder than whole ones.** 4 of 32 normal calls get a false warning mid-call although
  the whole-transcript false-positive rate is 3%: the score spikes when the caller asks for money and drops when
  the reassuring context arrives (`pl_neighbour_borrow_05`: 13, 5, 67, 89, 67, 67, 31; `pl_courier_real_07`
  peaks at 90 and 85 when the courier mentions 249 zł cash on delivery; `en_neighbour_borrow_02` peaks at 70).
- **Smoothing does its job for hang-ups.** Acting on a single reading would have hung up on the courier
  (90 → 85); the two-readings rule prevents it in the `full` view. In the `caller` view the same courier stays
  ≥ 90 twice and is hung up on: another argument for transcribing the senior.
- `2row` for warnings removes 1 of 4 false warnings but delays warnings by ~7 s (12 → 19 s median). Keep the
  server's `avg2` for warnings: a warning is cheap and reversible, a hang-up is not.
- One scam (`en_police_06`) never reaches a 2-reading mean ≥ 50 on basal alone; the rules catch it.

## Failure examples (production combination, `full` view)

- **False hang-ups (3):** `hw_en_normal_01` and `hw_pl_normal_08` are friends *telling the story* of a scam
  attempt ("he said he was my grandson … gift cards … don't tell mom and dad"): both rules (100) and basal
  (99 / 83) react to the script, not to who is asking. `pl_bank_real_02` is a genuine bank call saying "the bank
  never asks for BLIK codes, PIN or a transfer": the rules score 90 because regexes cannot read negation, while
  basal says 5. The "model ≥ 50 to hang up" policy removes this one.
- **Other false warnings:** `hw_pl_normal_06` / `hw_en_normal_03` (police officer inviting seniors to a
  scam-prevention talk; rules 77–78, basal 1–3), `pl_surprise_party_01/04` (money + "nikomu nie mów"; rules 72–88,
  basal 13–34), `pl_bank_real_03` (rules 62), `pl_courier_real_07` (cash on delivery 249 zł; basal 73),
  `pl_grandchild_secret_01` (basal 51), `hw_en_normal_05` (daughter asking to wire 1500 dollars; basal 56).
- **Scams basal-4.5B under-scores (rescued by the rules):** `en_police_04/06/07/10`, `en_grandchild_08`
  (basal 33–47). In `en_police_06` (sheriff, warrant, "wire the bond to the court's holding account") basal picks
  `scam_type = police` with 0.86 but puts P(low) at 0.67: it recognises the pattern but believes the call. More
  English police calls sit at 52–81, so hang-up recall in English is lower.
- **Scams the rules miss:** slow-build Polish grandchild calls score 12–38 (`pl_grandchild_accident_02…11`): the
  rules have no pattern for amounts written as digits (`30 tysięcy zł`, `5000 zł`), for `pożyczyć` (only the noun
  `pożyczka`), `koperta` or "przyjedzie kolega". Investment (3/15) and "new number" calls (1/8) stay below 50 because only
  one or two categories match (e.g. `blik`/`przelew` + urgency = 35) without a story element the rules know.
- **basal-1.5B** misses 6/16 Polish fake-bank calls (`pl_bank_security_01/02/04/06/09/15`, scores 6–25) and most
  hard hand-written scams.

## Interpretation and recommendations

1. **Keep `max(basal-4.5B, rules)` for the warning.** Recall 1.00 at FPR 0.07 on this set; the rules are a real
   safety net (they caught all 5 scams basal scored below 50), not just a fallback for outages.
2. **Do not let the rules alone trigger a hang-up.** Proposed: hang-up when the smoothed score ≥ 90 *and* basal ≥ 50
   in the same readings (on this data: FPR 0.02 → 0.01, recall 0.94 → 0.91). If basal is down (timeout, error),
   rules-only readings should warn but not hang up. Requiring a rule hit for hang-up (the planned
   `SECRECY_HANGUP_MIN` guard) costs recall (0.86) without removing the false hang-ups seen here.
3. **Keep warn at 50.** The sweep shows no better operating point: 40 adds false warnings (0.07 → 0.13 for the
   combination), 60 loses little but gains little. The rules' own threshold could go up (warn only when
   rules ≥ 80 if the model is below 50: FPR 0.07 → 0.05, recall 1.00 → 0.99); low priority.
4. **Transcribe the senior's side** (or at least pass it to the model) before relying on the model's precision in
   real calls. In the caller-only view the combination falsely warned on 26% of all normal calls and 34% of the
   hard negatives in this set.
5. **Fix rule gaps** (server branch): digit amounts (on the normalised text: `\b\d[\d ]* ?(?:zl|zlotych|tys)\w*`), `pożycz\w*` (verb),
   `koperc|kopert`, "przyjedzie (po|kolega)"; consider negation handling ("nigdy nie prosi o kod") or simply
   lowering rule-only scores when the bank/police text is a warning about scams.
6. **English police/government scams** are the model's weakest spot; the hard-coded rules cover them now. A
   follow-up could test the six-question schema (secrecy/authority/urgency) or `1 − P(scam_type = none)` as a
   second signal: averaging it with `risk_not_low` raised basal-4.5B warn recall from 0.97 to 0.99 at the same
   FPR in an offline check on the collected answers (hang-up recall dropped to 0.85, so not as a hang-up signal).
7. **basal-1.5B** only as an emergency fallback (e.g. GPU contention with two calls) and with a hang-up threshold
   around 70 (sweep: recall 0.70 at FPR 0.01).

## Limitations of this evaluation

- Synthetic text written by an AI from templates; family templates repeat phrasing; clean turn-taking; mild
  simulated recognition noise; no real audio (see `scenarios/README.md`).
- The same 300 calls were used to look at thresholds and policies; there is no held-out test set.
- Only the `risk` + `scam_type` tier was evaluated; the six-question tier and the alert summary were not.
- Speaker attribution is perfect here; a real pipeline with one mixed channel would also mix speakers.
- Rules are a snapshot of commit `bfffe0d`; later changes on the server branch are not reflected.

## Reproduce

```bash
uv run scenarios/generator/generate.py --stats
server/bench/run-basal.sh &                                              # basal-1.0-4.5B on :8000
BASAL_MODEL=~/models/sprawdzam/basal-1.0-1.5B BASAL_PORT=8001 server/bench/run-basal.sh &
uv run server/bench/eval/run_eval.py collect --url http://127.0.0.1:8000 --name basal-4.5B
uv run server/bench/eval/run_eval.py collect --url http://127.0.0.1:8000 --name basal-4.5B --view caller
uv run server/bench/eval/run_eval.py collect --url http://127.0.0.1:8001 --name basal-1.5B
uv run server/bench/eval/run_eval.py progressive --url http://127.0.0.1:8000 --name basal-4.5B --subset 64
uv run server/bench/eval/run_eval.py progressive --url http://127.0.0.1:8000 --name basal-4.5B --view caller --subset 64
uv run server/bench/eval/run_eval.py progressive --url http://127.0.0.1:8001 --name basal-1.5B --subset 64
uv run server/bench/eval/run_eval.py report
```
