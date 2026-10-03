# Model bench: Whisper (speech to text) and basal-1 (risk decisions) on a Mac

How we run the two self-hosted models on the development Mac, the HTTP APIs the backend talks to, and what we measured.
Everything here was run on an **Apple M4 Pro (20-core GPU), 48 GB RAM, macOS 27.0.1** on 3 Oct 2026.

## TL;DR

| | result |
|---|---|
| Whisper large-v3-turbo (whisper.cpp 1.9.4, Metal) | **~0.5 s per 2–4 s chunk** (p95 0.58 s), whole 22–34 s clip in 0.7–1.5 s. Phone-quality Polish is good on whole clips (WER 0.06–0.23) and acceptable on 4 s chunks (WER 0.07–0.18). 2 s chunks are clearly worse (WER up to 0.32). |
| basal-1.0-4.5B, upstream engine, 6 questions | 4.5 s p50 (MLX), 7.6 s (eager): too slow |
| basal-1.0-4.5B + our `--share-state` patch, MPS | **6 questions 1.94 s p50**, risk + scam_type 1.07 s, risk alone 0.76 s; peak memory 10.3 GB |
| basal-1.0-1.5B + `--share-state`, MPS | **6 questions 0.65 s p50**, risk alone 0.27 s; peak memory 4.9 GB; less separation between scams and normal calls |
| Answers (4.5B, 14 transcripts) | scam type 14/14 correct; `risk_not_low` = 100·(1 − P(low)) is 99 for every Polish scam and 0–5 for every normal call |
| Early detection (4.5B, turn by turn) | scams reach `risk_not_low` ≥ 50 after 1–3 turns (~7–19 s); one normal call (son borrowing money) spikes to 58 for one turn, so smoothing is required |

## Files

| path | what |
|---|---|
| `download-models.sh` | downloads Whisper and basal into `~/models/sprawdzam`, clones and patches the basal engine, creates its venv |
| `run-whisper.sh` | starts `whisper-server` on port 8080 |
| `run-basal.sh` | starts `basal-serve` on port 8000 (MPS + `--share-state` by default) |
| `stt/make_audio.sh` | macOS `say` → simulated phone line (300–3400 Hz, 8 kHz μ-law) → 16 kHz WAV, written to `~/models/sprawdzam/audio` |
| `stt/scripts/*.txt` | the five TTS scripts (PL/EN, scam/normal), also the WER reference |
| `stt/bench_whisper.py` | Whisper latency (whole clip, 2/3/4 s chunks), WER, missing keywords |
| `basal/transcripts/*.txt` | 10 Polish + 4 English speaker-tagged call transcripts (~60 s each; `pl_scam_*`, `pl_normal_*`, …) |
| `basal/schema_pl.json`, `basal/schema_en.json` | the six-question risk schema from `CLAUDE.md` (Polish and English wording) |
| `basal/bench_basal.py` | basal latency p50/p95, answers, server memory |
| `basal/progressive.py` | replays transcripts turn by turn and prints the risk after each turn |
| `basal/basal-share-state.patch` | our local patch to the basal engine (see below) |
| `results/*.json` | raw results of every run quoted in this file |

## Setup from zero (Mac, Apple Silicon)

Prerequisites: Homebrew `whisper-cpp` (1.9.4, provides `whisper-server`), `ffmpeg`, `uv`, `git`, the Hugging Face CLI
(`hf`), ~15 GB free disk.

```bash
brew install whisper-cpp ffmpeg uv huggingface-cli
server/bench/download-models.sh          # Whisper 1.6 GB + basal 9.5 GB + engine venv (~1 GB)
server/bench/run-whisper.sh              # terminal 1: http://127.0.0.1:8080
server/bench/run-basal.sh                # terminal 2: http://127.0.0.1:8000
```

Both servers bind to `127.0.0.1` by default, so they are not exposed on shared networks (e.g. hackathon Wi-Fi).
A natively running backend uses `http://127.0.0.1:8080` and `:8000`. The Docker backend container uses
`http://host.docker.internal:8080` and `:8000` (`WHISPER_URL`, `BASAL_URL` in `.env.example`); if Docker Desktop
cannot reach the localhost-bound servers, start them with `WHISPER_HOST=0.0.0.0` / `BASAL_HOST=0.0.0.0` and keep
the macOS firewall on.

Where the models live (outside the repo, never committed):

| path | size |
|---|---|
| `~/models/sprawdzam/whisper/ggml-large-v3-turbo.bin` | 1.6 GB |
| `~/models/sprawdzam/basal-1.0-4.5B/` (`model.safetensors` + tokenizer, `CALIBRATION.json`, exit heads) | 9.5 GB |
| `~/models/sprawdzam/basal-1.0-1.5B/` (optional lite model: `hf download Remek/basal-1.0-1.5B --local-dir …`) | 3.2 GB |
| `~/models/sprawdzam/basal-src/` (engine at `3fa2eea` + patch, `.venv` with torch 2.14.1, mlx 0.32.3, transformers 5.17.0) | 0.9 GB |

Start-up: `whisper-server` compiles its Metal kernels once (~17 s on the very first start, cached afterwards), then
loads in ~1–2 s. `basal-serve` answers `/health` ~7–10 s after start (weights already in the page cache; the first
read from disk after a reboot takes longer). **The first decision after start takes ~2 s (kernel compilation): the
backend should send one warm-up request at start-up.**

## whisper-server HTTP API

`run-whisper.sh` = `whisper-server --model ggml-large-v3-turbo.bin --host 127.0.0.1 --port 8080 --language pl
--threads 4 --no-timestamps --suppress-nst`.

`GET /health` → `{"status":"ok"}`

`POST /inference`, `multipart/form-data`:

| field | value |
|---|---|
| `file` | audio file; send **16 kHz mono PCM s16le WAV** (the server can convert other formats only with `--convert` + ffmpeg) |
| `language` | `pl` or `en`; always send it (forced from the senior's settings), otherwise the server default (`pl`) is used |
| `response_format` | `json` (just text), `verbose_json` (segments, `avg_logprob`, `no_speech_prob`), `text`, `srt`, `vtt` |
| `temperature`, `temperature_inc` | `0.0` and `0.2` (fallback on decoder failure; keep it, it stops repetition loops) |
| `no_speech_thold` | optional, default 0.6 |
| `prompt` | optional initial prompt. **Not recommended:** with `"…BLIK, policja, kaucja, wnuczek."` it invented a first word on a 4 s chunk |

```bash
curl -s http://127.0.0.1:8080/inference -F file=@chunk.wav -F language=pl -F response_format=json
```

Response (real, 34 s phone-quality clip, 1.45 s):

```json
{"text":" Dzień dobry, tu aspirant Jan Kowalski z Komendy Miejskiej Policji w Krakowie. Dzwonię w bardzo pilnej sprawie. Pani wnuczek Michał spowodował dzisiaj wypadek samochodowy, ranna jest kobieta w ciurze. Żeby nie trafił do aresztu, potrzebna jest kaucja w wysokości 30 tysięcy złotych. Proszę nikomu o tym nie mówić, ani córce, ani w banku, bo to utrudni śledztwo. Może pani przekazać gotówkę naszemu kurierowi albo podać kod blik.\n Idę w domu, musimy działać natychmiast, prokurator czeka.\n"}
```

`verbose_json` (real, 4 s chunk, tokens shortened):

```json
{"task": "transcribe", "language": "polish", "duration": 4.0,
 "text": " spowodował dzisiaj wypadek samochodowy, ranna jest kobieta w\n",
 "segments": [{"id": 0, "text": " spowodował dzisiaj wypadek samochodowy, ranna jest kobieta w",
               "tokens": [637, 305, 378], "temperature": 0.0, "avg_logprob": -0.0758, "no_speech_prob": 5.6e-11}],
 "detected_language": "polish", "detected_language_probability": 0.9992, "language_probabilities": {"pl": 0.9992}}
```

Notes for the backend client:

- The text starts with a space and may contain `\n`; strip it.
- Numbers come out as digits and currency as symbols/abbreviations (`30 tysięcy`, `200 zł`, `$20`): keyword rules
  must match `\d+ ?(zł|złotych|tys)` and not only number words.
- A known Whisper hallucination appeared on a trailing chunk: `KONIEC` (“the end”). Drop chunks that are mostly
  silence (VAD before Whisper) and consider ignoring segments with high `no_speech_prob` (use `verbose_json`).
- One request at a time is processed; requests queue up in the server.
- `--audio-ctx 256` cut encoder time from 650 to 170 ms on a 4 s chunk but produced `... ... ...` garbage: do not use.

## basal-serve HTTP API (`POST /v1/systemone`)

`run-basal.sh` = `basal-serve --model ~/models/sprawdzam/basal-1.0-4.5B --name basal-1.0-4.5B --mode mps --host 127.0.0.1
--port 8000 --share-state`. Other endpoints: `GET /health` → `{"status": "ok"}`, `GET /v1/models` →
`{"models": [{"name": "basal-1.0-4.5B", "release_date": "2026-10-01", "mode": "mps", "early_exit": [], …}]}`.

Request (real; the full six-question schema is in `basal/schema_pl.json`):

```json
{
  "state": "Dzwoniący: Dzień dobry, aspirant Jan Kowalski, Komenda Miejska Policji w Krakowie. Pani wnuczek Michał spowodował wypadek, potrzebna jest kaucja trzydzieści tysięcy złotych.\nSenior: Jezus Maria, ile mam w domu, może dziesięć tysięcy.\nDzwoniący: Proszę nikomu o tym nie mówić, ani córce, ani w banku. Za godzinę przyjedzie po pieniądze nasz kurier. Musimy działać natychmiast.",
  "questions": {
    "money": {"type": "noul", "instructions": "Czy dzwoniący prosi o pieniądze, przelew, przekazanie gotówki lub kod BLIK?"},
    "scam_type": {"type": "choice", "instructions": "Który schemat oszustwa najlepiej pasuje do tej rozmowy?", "option_keys": "hide",
      "criteria": {"none": "Zwykła rozmowa, brak oszustwa", "grandchild": "Krewny w tarapatach potrzebuje pieniędzy (metoda na wnuczka)",
                   "police": "Fałszywy policjant lub prokurator", "bank": "Fałszywy pracownik banku, zagrożone konto", "other": "Inny rodzaj oszustwa"}},
    "risk": {"type": "score", "instructions": "Jak bardzo prawdopodobne jest, że ta rozmowa to próba oszustwa?", "option_keys": "hide",
      "criteria": {"low": "Brak sygnałów ostrzegawczych", "medium": "Pewne sygnały ostrzegawcze", "high": "Wyraźny schemat oszustwa",
                   "critical": "Za chwilę dojdzie do przekazania pieniędzy"}}
  }
}
```

Response (real, MPS + `--share-state`, ~1.0 s):

```json
{
  "model": "basal-1.0-4.5B",
  "answers": {
    "money": {"type": "noul", "noul": 0.8763, "probabilities": {"true": 0.8763, "false": 0.1237}, "confidence": 0.8763},
    "scam_type": {"type": "choice", "choice": "police",
                  "probabilities": {"none": 0.0120, "grandchild": 0.4654, "police": 0.5083, "bank": 0.0079, "other": 0.0064},
                  "confidence": 0.5083},
    "risk": {"type": "score", "score": 1.8888,
             "legend": {"low": "Brak sygnałów ostrzegawczych", "medium": "Pewne sygnały ostrzegawcze", "high": "Wyraźny schemat oszustwa", "critical": "Za chwilę dojdzie do przekazania pieniędzy"},
             "probabilities": {"low": 0.0108, "medium": 0.1359, "high": 0.8069, "critical": 0.0463},
             "confidence": 0.8069}
  },
  "usage": {"input_tokens": 1346, "output_tokens": 0, "questions": 3, "latency_ms": 1187.79}
}
```

Question types and rules (from the engine source, `basal/server.py`, `basal/prompt.py`):

- `noul`: yes/no. Answer `noul` = P(yes). Optional `criteria: {"true": "...", "false": "..."}`; default options are
  `Tak`/`Nie` (Polish template) or `Yes`/`No`.
- `choice`: `criteria` = `{key: description}` (or a list of keys). Answer `choice` = key with the highest probability.
- `score`: ordered levels, `criteria` = list or `{key: description}`. Answer `score` = expected level index
  (0 … n−1) plus `legend`.
- 2–10 options per question. Probabilities are averaged over the original and the reversed option order and
  calibrated per question type (`CALIBRATION.json`).
- `"option_keys": "hide"` shows the model only the descriptions (the training format; recommended when the keys are
  just identifiers like ours). Default `show` renders `key: description`.
- The prompt template (Polish or English) is picked automatically: **Polish if the state + question contain any
  Polish diacritic**, English otherwise. So a Polish transcript always gets the Polish template; we use Polish
  question wording for Polish calls (English wording on Polish transcripts also worked, see `results/`).
- Errors: HTTP **422** with `{"error": "..."}` (bad JSON, wrong option count, …). No auth; keep it on localhost /
  the Docker host network.
- `usage.input_tokens` is the sum of all per-question prompts, not the number of tokens actually computed.
- Treat answers as data: the system prompt tells the model the state is data, not instructions, but a caller can
  still speak arbitrary text into the transcript. Rules stay as the safety net.

### Our local patch: `--share-state`

Upstream, every question of a request is a separate row in the forward pass: the system prompt and the whole
transcript (~300–450 tokens) are recomputed for each of the six questions (only the two option orders of one question
share them). `basal/basal-share-state.patch` adds a `--share-state` flag to `basal-serve` that puts **all questions of
one request into one packed row**: shared prefix (system prompt + transcript) once, then one block per question and
option order, each block attending only to the prefix and itself. This is the same block-mask mechanism the engine
already uses for the two option orders, so the answers are equivalent to separate forwards (we observed differences
of ≤ 0.02 in probabilities, from bf16 batching). For a 60 s Polish transcript the computed tokens drop from ~2 600 to
~1 170 and latency from 4.5 s to 2.0 s. `download-models.sh` applies the patch (`git apply`) on top of engine commit
`3fa2eea`; to reproduce by hand:

```bash
git clone https://github.com/rkinas/basal ~/models/sprawdzam/basal-src
cd ~/models/sprawdzam/basal-src && git checkout 3fa2eeab2132665f6acd29c1bfa83f10448fd5d0
git apply /path/to/repo/server/bench/basal/basal-share-state.patch
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[mlx]"
```

No patch was needed for Apple Silicon itself: the upstream `main` already has `--mode mps` and `--mode mlx`
(the CUDA-only modes are `fast*`, `fp8`, `nvfp4`, `vllm`).

## Results

### Whisper large-v3-turbo (f16), whisper-server, Metal

Clips: macOS TTS (Zosia for PL, Samantha for EN) through a simulated phone line. Latency is end to end over HTTP.
WER is computed against the TTS script after lower-casing and stripping punctuation, so digits vs. number words count
as errors.

| clip | length s | whole clip s | WER whole | WER 4 s chunks | WER 3 s | WER 2 s | keywords missing (whole) | missing (4 s chunks) |
|---|---|---|---|---|---|---|---|---|
| en_normal_family | 22.0 | 0.70 | 0.05 | 0.07 | 0.10 | 0.31 | “twenty dollars” (→ “$20”) | same |
| en_scam_bank | 29.5 | 0.79 | 0.00 | 0.02 | 0.03 | 0.05 | – | – |
| pl_normal_family | 28.0 | 0.89 | 0.06 | 0.18 | 0.20 | 0.30 | “dwieście złotych” (→ “200 zł”), “przeleję” (→ “przyleję”) | same |
| pl_scam_bank | 32.6 | 1.35 | 0.23 (one sentence skipped) | 0.15 | 0.20 | 0.32 | “nikim” | “kredyt”, “sms” |
| pl_scam_police | 34.4 | 1.45 | 0.09 | 0.08 | 0.14 | 0.18 | – | – |

| request | n | p50 | p95 | max |
|---|---|---|---|---|
| 2 s chunk | 74 | 0.50 s | 0.53 s | 0.61 s |
| 3 s chunk | 51 | 0.51 s | 0.57 s | 1.10 s |
| 4 s chunk | 39 | 0.53 s | 0.58 s | 0.60 s |
| whole clip (22–34 s) | 5 | 0.89 s | – | 1.45 s |
| 3 s chunk while basal runs back-to-back on the same GPU | 51 | 1.26 s | 1.46 s | 4.35 s |

Latency barely depends on chunk length because the encoder always processes a 30 s window. That means a longer
chunk costs almost nothing extra and is more accurate: **cut at VAD pauses into 3–8 s utterances rather than fixed
2 s pieces.** Not tried: the q5_0/q8_0 quantised model (latency was not borderline) and Parakeet (plan B).

### basal-1 latency (end to end over HTTP, after 1–2 warm-up requests)

14 transcripts (10 PL, 4 EN), 2–3 repeats each unless noted. A Polish 60 s transcript is ~300–400 tokens of state.

| model | mode | share-state | questions | p50 | p95 | peak memory footprint¹ |
|---|---|---|---|---|---|---|
| 4.5B | eager (PyTorch on MPS) | – | 6 | 7.64 s² | 8.22 s | 11.5 GB |
| 4.5B | eager | – | risk | 1.29 s² | 1.31 s | |
| 4.5B | mlx | – | 6 | 4.53 s | 5.68 s | 20.1 GB |
| 4.5B | mlx | yes | 6 | 2.05 s | 2.51 s | up to 32.7 GB³ |
| 4.5B | mlx | yes | 4 yes/no (money, secrecy, authority, urgency) | 1.18 s | 1.50 s | |
| 4.5B | mlx | yes | risk + scam_type | 1.02 s | 1.27 s | |
| 4.5B | mlx | yes | risk | 0.73 s | 0.90 s | |
| 4.5B | mlx, `--orders 1` | yes | 6 | 1.14 s | 1.41 s | |
| 4.5B | mlx, `--orders 1` | yes | risk | 0.66 s | 0.82 s | |
| **4.5B** | **mps** | **yes** | **6** | **1.94 s** | **2.39 s** | **10.3 GB** |
| **4.5B** | **mps** | **yes** | **risk + scam_type** | **1.07 s** | **1.35 s** | |
| **4.5B** | **mps** | **yes** | **risk** | **0.76 s** | **0.98 s** | |
| 4.5B | mps | yes | risk + scam_type, while Whisper runs back-to-back | 1.67 s | 2.05 s | |
| 1.5B | mps | yes | 6 | 0.65 s | 0.79 s | 4.9 GB |
| 1.5B | mps | yes | risk + scam_type | 0.39 s | 0.46 s | |
| 1.5B | mps | yes | risk | 0.27 s | 0.33 s | |

¹ `peak memory footprint` from `/usr/bin/time -l` for the whole server run (includes Metal buffers; RSS alone
misses them). ² 6 Polish transcripts, 1 repeat. ³ MLX keeps freed buffers in its cache; the same request in a
single-threaded test peaked at 10.1 GB, so the growth is likely per executor thread in the server. MPS gives the same
speed with a third of the memory, hence the default.

### basal-1 answers (full 60 s transcripts, six questions)

4.5B in mode mps + share-state (MLX and eager gave the same answers within ±0.02); last two columns: 1.5B.
`risk (exp. level)` = expected level / 3 × 100; `risk not-low` = 100 × (1 − P(low)).

| transcript | expected | money | secrecy | authority | urgency | scam_type | risk (exp. level) | risk not-low | 1.5B scam_type | 1.5B not-low |
|---|---|---|---|---|---|---|---|---|---|---|
| en_normal_01_grandson | normal | 0.79 | 0.09 | 0.01 | 0.08 | none (0.79) | 2 | 4 | none (0.80) | 6 |
| en_normal_02_surgery | normal | 0.01 | 0.03 | 0.03 | 0.10 | none (1.00) | 0 | 1 | none (0.95) | 3 |
| en_scam_01_bank | scam/bank | 0.26 | 0.90 | 0.63 | 0.96 | bank (0.95) | 65 | 99 | bank (0.88) | 96 |
| en_scam_02_grandchild | scam/grandchild | 0.63 | 0.90 | 0.22 | 0.93 | grandchild (0.88) | 32 | 64 | grandchild (0.69) | 89 |
| pl_normal_01_lunch | normal | 0.44 | 0.02 | 0.00 | 0.35 | none (0.98) | 3 | 5 | none (0.89) | 23 |
| pl_normal_02_son_loan | normal | 0.88 | 0.04 | 0.00 | 0.09 | none (0.94) | 1 | 3 | none (0.90) | 20 |
| pl_normal_03_clinic | normal | 0.00 | 0.01 | 0.01 | 0.07 | none (1.00) | 0 | 0 | none (0.98) | 3 |
| pl_normal_04_courier | normal | 0.40 | 0.01 | 0.01 | 0.40 | none (1.00) | 1 | 2 | none (0.95) | 7 |
| pl_normal_05_neighbour | normal | 0.01 | 0.02 | 0.03 | 0.21 | none (0.99) | 0 | 0 | none (0.59) | 3 |
| pl_scam_01_police | scam/police | 0.86 | 0.99 | 0.94 | 0.98 | police (0.87) | 63 | 99 | police (0.64) | 96 |
| pl_scam_02_grandchild | scam/grandchild | 0.87 | 0.95 | 0.08 | 0.97 | grandchild (0.99) | 63 | 99 | grandchild (0.97) | 99 |
| pl_scam_03_bank | scam/bank | 0.97 | 0.94 | 0.40 | 0.98 | bank (0.99) | 63 | 99 | bank (0.98) | 98 |
| pl_scam_04_cbs | scam/police | 0.94 | 0.97 | 0.92 | 0.80 | police (0.97) | 63 | 99 | police (0.38) | 91 |
| pl_scam_05_investment | scam/other | 0.94 | 0.24 | 0.29 | 0.97 | other (0.81) | 64 | 99 | other (0.81) | 100 |

- `scam_type` is right 14/14 for both models.
- The model almost never picks `critical` (“money is about to be handed over”): scams land on `high`, so the
  expected level stays at ~63–65 and **would never reach the hang-up threshold of 80**. `risk not-low` separates
  much better (4.5B: scams 64–99, normal calls 0–5).
- `money` alone is not a scam signal: the son asking his father for a loan scores 0.88 (correct, but harmless).
  `secrecy` is the cleanest single signal (normal ≤ 0.09, Polish scams ≥ 0.94 except the investment scam).
- 14 hand-written transcripts are a smoke test, not an evaluation; thresholds must be tuned on `scenarios/`.

### Turn by turn (risk only, `progressive.py`)

`risk not-low` after each turn of the dialogue (state = all turns so far). 4.5B:

```
en_normal_01_grandson          3   2  12   7   7   8   7   7   4
en_normal_02_surgery           4   3   2   2   2   2   1   1   1
en_scam_01_bank               90  69  95  84  97  96  99  99  99   -> >= 50 at turn 1 (~8 s)
en_scam_02_grandchild          7   6   4   5  62  71  71  63  67   -> >= 50 at turn 5 (~36 s)
pl_normal_01_lunch             2   1   1   1   5   9  14   9   6   5
pl_normal_02_son_loan          2   1  58  18  12   8   5   4   3   3   -> one-turn spike (asks to borrow 500 zł)
pl_normal_03_clinic            4   3   3   1   1   1   1   1   0   0
pl_normal_04_courier          29   5  18  12   5   7   3   2
pl_normal_05_neighbour         2   1   2   1   2   1   1   1   0   0
pl_scam_01_police             30  46  85  70  71  87  94  90  99   -> >= 50 at turn 3 (~19 s)
pl_scam_02_grandchild         20  48  98  97  98  98  98  98  98   -> >= 50 at turn 3 (~19 s)
pl_scam_03_bank               15  11  85  94  96  96  99  99  99   -> >= 50 at turn 3 (~14 s)
pl_scam_04_cbs                79  91  97  97  99  98  99   -> >= 50 at turn 1 (~7 s)
pl_scam_05_investment         98  95  99  98  99  98  99  99  99   -> >= 50 at turn 1 (~8 s)
```

With “two consecutive readings ≥ 50” every scam is still caught by turn 3–6 and the son-loan spike is ignored. The
1.5B (`results/progressive_1.5B.json`) has no normal call above 50 either, but normal calls drift up to 38 and two
Polish scams are caught later (turns 4–7).

## Recommendations for the backend

1. **Keep basal-1.0-4.5B** (no need for Clef-Flash), served with `run-basal.sh` (mode `mps` + `--share-state`).
2. **Two-tier questions.** Every 3–4 s ask only `risk` (+ `scam_type` if you want it on the panel): 0.8–1.1 s.
   When the smoothed risk crosses the warning threshold, ask the full six-question schema once (~2 s) to build the
   alert summary (which signals fired).
3. **Use `risk_not_low = 100 × (1 − P(low))`** (or P(high) + P(critical)) as the 0–100 risk, not the expected level.
   Starting point: warn at ≥ 50 for two consecutive readings; hang up / family password at ≥ 90 for two consecutive
   readings *and* (`secrecy` ≥ 0.8 or a keyword rule hit). Tune on `scenarios/`.
4. **Timeouts:** basal 3 s, Whisper 3 s (both share one GPU; under full contention p95 was ~2 s / ~1.5 s). On timeout
   or HTTP 422/5xx fall back to the keyword rules and log it, as planned.
5. **Whisper input:** VAD-cut 3–8 s utterances, `language` always set, strip text, match digits in rules.
6. **Warm-up request** to both servers at backend start-up.
7. **If latency or GPU contention becomes a problem** (two calls at once, AWS without GPU): basal-1.0-1.5B with the
   same API (`BASAL_MODEL=~/models/sprawdzam/basal-1.0-1.5B server/bench/run-basal.sh`), 3× faster, a bit noisier.

## Reproducing the measurements

```bash
server/bench/stt/make_audio.sh
uv run server/bench/stt/bench_whisper.py --url http://127.0.0.1:8080 --out server/bench/results/whisper_large-v3-turbo.json
uv run server/bench/basal/bench_basal.py --url http://127.0.0.1:8000 --pid "$(pgrep -f bin/basal-serve | head -1)" \
  --out server/bench/results/basal_mps_share_6q.json
uv run server/bench/basal/bench_basal.py --questions risk,scam_type --out server/bench/results/basal_mps_share_q-risk-scam_type.json
uv run server/bench/basal/progressive.py --out server/bench/results/progressive_4.5B.json
# peak memory: start the server as  /usr/bin/time -l server/bench/run-basal.sh  and stop it with Ctrl-C
```

Other modes: `BASAL_MODE=mlx|eager`, `BASAL_SHARE_STATE=0`, extra flags are passed through (e.g.
`server/bench/run-basal.sh --orders 1`).
