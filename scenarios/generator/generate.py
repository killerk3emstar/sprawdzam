# /// script
# requires-python = ">=3.11"
# ///
"""Generate scenarios/calls.jsonl: synthetic phone-call transcripts for evaluating the risk engine.

    uv run scenarios/generator/generate.py            # writes scenarios/calls.jsonl (deterministic)
    uv run scenarios/generator/generate.py --stats    # also prints the composition

Every call is built from a family template (pl.py, en.py) with per-call random slots and variant
choices, then passed through `whisperify` (casing, punctuation, recognition errors). Hand-written
calls (handwritten.py) are added as they are. The RNG is seeded from the call id, so the output is
identical on every run.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import en  # noqa: E402
import handwritten  # noqa: E402
import pl  # noqa: E402
from common import fill, whisperify  # noqa: E402

# calls per family (templated); hand-written calls come on top
COUNTS = {
    "pl_grandchild_accident": 14, "pl_grandchild_doctor": 6, "pl_grandchild_newnumber": 8, "pl_police_bail": 10,
    "pl_police_cbs": 12, "pl_bank_security": 16, "pl_investment": 8, "pl_other_scam": 8,
    "pl_family_chat": 13, "pl_friend_chat": 5, "pl_wrong_number": 2, "pl_family_money": 11, "pl_grandchild_secret": 6,
    "pl_surprise_party": 5, "pl_bank_real": 9, "pl_courier_real": 7, "pl_medical": 7, "pl_neighbour_borrow": 6,
    "pl_police_real": 6, "pl_admin_real": 3, "pl_sales_legit": 2,
    "en_grandchild": 14, "en_police": 11, "en_bank": 12, "en_investment": 7, "en_other_scam": 10,
    "en_family_chat": 10, "en_wrong_number": 2, "en_family_money": 8, "en_surprise_party": 4, "en_grandchild_secret": 4,
    "en_bank_real": 6, "en_delivery_real": 5, "en_medical": 5, "en_neighbour_borrow": 3, "en_police_real": 4,
    "en_handyman_real": 2, "en_church_real": 1,
}
SCAM_HARD_SHARE = 0.45


def build_templated():
    calls = []
    for lang_mod in (pl, en):
        for family, (builder, label, scam_type) in lang_mod.FAMILIES.items():
            lang = family[:2]
            for k in range(1, COUNTS[family] + 1):
                cid = f"{family}_{k:02d}"
                r = random.Random(cid)
                slots = lang_mod.slots(r)
                if label == "scam":
                    hard = r.random() < SCAM_HARD_SHARE
                    difficulty = "hard" if hard else "easy"
                else:
                    hard = r.random() < 0.5  # extra lines in some normal builders
                    difficulty = "hard" if family in lang_mod.HARD_NEGATIVE_FAMILIES else "easy"
                raw = builder(r, slots, hard)
                noise = r.uniform(0.5, 1.5)
                turns = []
                for speaker, text in raw:
                    text = fill(text, slots)
                    assert "{" not in text, (cid, text)
                    text = whisperify(text, lang, r, noise)
                    if text:
                        turns.append({"speaker": speaker, "text": text})
                calls.append({"id": cid, "lang": lang, "label": label, "scam_type": scam_type, "difficulty": difficulty,
                              "source": "template", "family": family[3:], "turns": turns})
    return calls


def build_handwritten():
    return [{"id": f"hw_{suffix}", "lang": lang, "label": label, "scam_type": st, "difficulty": diff, "source": "handwritten",
             "family": "handwritten", "turns": [{"speaker": sp, "text": tx} for sp, tx in turns]}
            for suffix, lang, label, st, diff, turns in handwritten.CALLS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE.parent / "calls.jsonl"))
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    calls = build_templated() + build_handwritten()
    ids = [c["id"] for c in calls]
    assert len(ids) == len(set(ids)), "duplicate ids"
    with open(a.out, "w") as f:
        for c in calls:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"wrote {len(calls)} calls to {a.out}")
    if a.stats:
        print(Counter(c["lang"] for c in calls), Counter(c["label"] for c in calls))
        print(Counter((c["lang"], c["label"]) for c in calls))
        print(Counter((c["label"], c["difficulty"]) for c in calls))
        print(Counter(c["scam_type"] for c in calls))
        print(Counter(c["source"] for c in calls))
        nturns = [len(c["turns"]) for c in calls]
        words = [sum(len(t["text"].split()) for t in c["turns"]) for c in calls]
        print(f"turns min/median/max {min(nturns)}/{sorted(nturns)[len(nturns)//2]}/{max(nturns)}; "
              f"words min/median/max {min(words)}/{sorted(words)[len(words)//2]}/{max(words)}")
        texts = Counter(" ".join(t["text"] for t in c["turns"]) for c in calls)
        print("exact duplicate transcripts:", sum(v - 1 for v in texts.values() if v > 1))


if __name__ == "__main__":
    main()
