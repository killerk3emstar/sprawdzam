# Scenarios: synthetic phone-call transcripts (PL/EN)

300 synthetic transcripts of phone calls to older people, used to evaluate the scam-risk engine
(keyword rules, basal-1 models and their combination; see `server/bench/eval/`).
**All calls are synthetic.** None of them is a recording or transcript of a real call.

| | Polish | English | total |
|---|---|---|---|
| scam | 90 | 60 | 150 |
| normal | 90 | 60 | 150 |
| total | 180 | 120 | 300 |

- Difficulty: scams 77 easy / 73 hard; normal calls 35 easy / 115 hard (hard negatives).
- Scam types: grandchild 45, police 34, bank 31, investment 17, other 23.
- 272 template-generated calls, 28 fully hand-written calls (`hw_*`).
- 4–17 turns per call (median 10), 17–142 words (median 72), i.e. roughly 10–60 s of speech:
  about one rolling 60 s transcript window of the backend.

## Files

| path | what |
|---|---|
| `calls.jsonl` | the dataset, one call per line |
| `generator/generate.py` | rebuilds `calls.jsonl` (`uv run scenarios/generator/generate.py --stats`); deterministic |
| `generator/pl.py`, `generator/en.py` | call families (templates with variant phrases and slots) |
| `generator/handwritten.py` | 28 hand-written calls (hardest cases, mixed PL/EN) |
| `generator/common.py` | slot filling and the Whisper-style noise step |

## Format

```json
{"id": "pl_police_cbs_03", "lang": "pl", "label": "scam", "scam_type": "police", "difficulty": "hard",
 "source": "template", "family": "police_cbs",
 "turns": [{"speaker": "caller", "text": "dzień dobry cbśp komisarz paweł sowa"}, {"speaker": "senior", "text": "słucham?"}]}
```

| field | values |
|---|---|
| `id` | `<lang>_<family>_<nn>` for template calls, `hw_<lang>_<scam\|normal>_<nn>` for hand-written ones |
| `lang` | `pl` or `en` (the dominant language; a few calls mix both) |
| `label` | `scam` or `normal` |
| `scam_type` | `none` (normal calls), `grandchild`, `police`, `bank`, `investment`, `other` |
| `difficulty` | `easy` or `hard` (definitions below) |
| `source`, `family` | `template` + family name, or `handwritten` |
| `turns` | list of `{speaker: caller\|senior, text}` in call order |

## Label definitions

- **scam**: the caller tries to get money, payment credentials (card number, PIN, BLIK or SMS code, banking
  login) or remote access to a device by deception. The label is about intent; the call may end before
  any money is mentioned (e.g. `hw_pl_scam_01` only prepares a fake-police "operation").
- **normal**: any legitimate call, including calls that talk about money, secrets, the police or banks.
- **scam_type**:
  - `grandchild`: a relative (or someone on their behalf: lawyer, doctor, friend) in trouble needs money now
    ("na wnuczka", "Mum, I changed my number", fake doctor calling about a grandchild);
  - `police`: fake police officer, CBŚ agent, prosecutor, sheriff or court officer;
  - `bank`: fake bank employee or bank security team ("safe account", codes, remote-access app);
  - `investment`: crypto/stock "opportunities", guaranteed returns, fake account managers;
  - `other`: everything else (fake utility/gas worker, lottery prize, tax/pension refund, parcel customs fee,
    tech support, fake charity, inheritance fee, government agencies such as IRS/SSA/Medicare/ZUS).
  The basal schema has no `investment` option, so for the model `investment` counts as `other`.
- **difficulty = easy** (scams): the classic script appears early: authority or relative + money + urgency,
  often secrecy. **easy** (normal): plain family/friend chats and wrong numbers.
- **difficulty = hard** (scams): slow build-up (small talk first), polite tone, the money request comes late
  or is indirect ("help me out", "the envelope in your wardrobe"), no secrecy request, a fake "verify by
  calling 997/112" step, or mixed PL/EN. **hard** (normal), i.e. hard negatives: a real relative borrowing
  money, a grandchild's secret without money, a surprise party (money + "don't tell anyone"), a real bank
  call (card expiry, fraud check that points to official channels), a real courier with cash on delivery,
  clinic/pharmacy/private doctor fees, a neighbour borrowing cash, real police (witness, found wallet,
  scam-prevention talk), a building administrator or plumber, legitimate telemarketing, and friends
  *telling the story* of a scam attempt.

## How it was generated

Written by Claude Code (model Claude Opus 5.5) for this project on 3 Oct 2026, then spot-checked by reading
samples; the team reviews it. No external text was copied.

1. **Templates** (`pl.py`, `en.py`): each family is a function that builds the dialogue beat by beat
   (opening, story, request, objection, pressure, secrecy, closing). Every beat has 2–5 hand-written variants;
   some beats are optional. Per-call slots fill in the senior's and the grandchild's gender (Polish grammar),
   names, cities, fictional bank names and amounts (`30 tysięcy zł`, `30 000 zł`, `30 tys. zł`, `$3,000`).
2. **Whisper-style noise** (`common.py: whisperify`): ~65% of turns are lower-cased, ~12% lose all
   punctuation, others lose some commas or the final full stop; numbers are already digits. With a per-call
   noise level (0.5–1.5×): recognition confusions, some observed in our Whisper bench (`przeleję` →
   `przyleję`, `ciąży` → `ciurze`, `blik` → `blig`, `bail` → `bale`, `gift cards` → `gift guards`), a dropped
   word, a doubled word or a leading filler (`yyy`, `no`, `uh`, `so`). Keywords are deliberately hit too.
3. **Hand-written calls** (`handwritten.py`) are already in Whisper style and get no extra noise.
4. The RNG is seeded from each call id, so `generate.py` always produces the same file (checked: 0 exact
   duplicate transcripts).

## Known biases and limitations

- **Synthetic and written by the same kind of model we evaluate against.** Scams follow the scripts described
  by Polish police and bank warnings, which a language model also knows well; real scammers improvise, talk
  over the senior and use silence. Results on this set are an optimistic upper bound for real calls.
- **Template families repeat phrasing.** Within a family, calls share beats; a model or rule that learns a
  phrase can look better than it is. Per-family results in `server/bench/eval/RESULTS.md` show this.
- **Clean turn-taking.** Real Whisper output would split and merge utterances at pauses, mix up speakers, and
  drop whole sentences; here each turn is one clean utterance with mild noise.
- **Text only, no audio.** The noise imitates recognition errors on text; it is not the output of Whisper on
  real phone audio. Only 5 TTS clips went through the real STT path (see `server/bench/README.md`).
- **Short calls.** Each call is about one 60 s window; long calls where the scam starts after minutes of small
  talk are not covered.
- **Language mix**: Polish 60%, English 40%; only a handful of mixed PL/EN calls (`hw_pl_scam_02`,
  `hw_pl_normal_05`, `hw_en_scam_06`).
- **Labels are ours.** Some normal calls are debatable (telemarketing, a grandchild asking to keep a secret).
- Names are common placeholder names (e.g. "Kowalski", "Jamie"), bank and company names are fictional, phone
  numbers are obviously fake (`500 000 000`, `555 0100`). Any resemblance to real people is unintended.

## License

Written for this project; released under **CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/).
Attribution: "Sprawdzam / Second Ear scam-call scenarios, HackYeah 2026".
