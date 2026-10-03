# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""How early does basal flag a scam, and do normal calls stay low while they are still short?

Replays every transcript turn by turn (state = all turns so far, like the live rolling window during a call) and asks
only the `risk` question. Prints risk_not_low = 100 * (1 - P(low)) after each turn, so you can see at which turn a call
would cross the warning / hang-up thresholds.

    uv run server/bench/basal/progressive.py --url http://127.0.0.1:8000 --out server/bench/results/progressive.json
"""
import argparse
import json
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--transcripts", default=str(HERE / "transcripts"))
    ap.add_argument("--glob", default="*.txt")
    ap.add_argument("--warn", type=int, default=50)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    client = httpx.Client(timeout=120)
    out = {}
    for f in sorted(Path(a.transcripts).glob(a.glob)):
        lang = f.name[:2]
        risk_q = {"risk": json.loads((HERE / f"schema_{lang}.json").read_text())["risk"]}
        turns = [t for t in f.read_text().strip().splitlines() if t.strip()]
        words, series = 0, []
        for k in range(1, len(turns) + 1):
            words += len(turns[k - 1].split())
            r = client.post(f"{a.url}/v1/systemone", json={"state": "\n".join(turns[:k]), "questions": risk_q})
            r.raise_for_status()
            p = r.json()["answers"]["risk"]["probabilities"]
            series.append({"turn": k, "words": words, "approx_s": round(words / 2.5), "not_low": round(100 * (1 - p["low"]))})
        first = next((s for s in series if s["not_low"] >= a.warn), None)
        out[f.stem] = {"series": series, "first_warn": first}
        print(f"{f.stem:28s} " + " ".join(f"{s['not_low']:3d}" for s in series)
              + (f"   -> >= {a.warn} at turn {first['turn']} (~{first['approx_s']} s)" if first else "   -> never"),
              flush=True)
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
        print("wrote", a.out)


if __name__ == "__main__":
    main()
