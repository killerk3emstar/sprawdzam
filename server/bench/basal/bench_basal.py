# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Latency and answers of a running basal-serve (POST /v1/systemone) on speaker-tagged call transcripts.

Each transcript (transcripts/*.txt, ~60 s of dialogue) becomes one request with the six questions of the risk schema
(schema_pl.json for pl_* files, schema_en.json for en_*). After warm-up every transcript is sent --repeats times;
latency is measured on the client (end to end, what the backend will see) and reported as p50 / p95.

    uv run server/bench/basal/bench_basal.py --url http://127.0.0.1:8000 --out server/bench/results/basal_mlx.json
    uv run server/bench/basal/bench_basal.py --schema en          # English questions for every transcript
    uv run server/bench/basal/bench_basal.py --questions risk     # only one question per request
    uv run server/bench/basal/bench_basal.py --pid $(pgrep -f basal-serve)   # also sample the server's memory

Risk 0-100 = expected level of the 4-level `risk` score / 3 * 100 (low=0, medium=33, high=67, critical=100).
risk_not_low = 100 * (1 - P(low)): the model rarely picks "critical", so this separates scams from normal calls better.
"""
import argparse
import json
import statistics
import subprocess
import threading
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
EXPECTED_TYPE = {"police": "police", "cbs": "police", "grandchild": "grandchild", "bank": "bank",
                 "investment": "other"}


def expected(name):
    """pl_scam_01_police -> ("scam", "police"); pl_normal_02_son_loan -> ("normal", "none")."""
    parts = name.split("_")
    label = parts[1]
    return label, (EXPECTED_TYPE.get(parts[3], "other") if label == "scam" else "none")


def footprint_mb(pid):
    """Physical footprint of a process in MB (includes Metal/unified-memory allocations), via macOS `footprint`."""
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
            subprocess.run(["footprint", "-p", str(pid), "-f", "bytes", "-j", tmp.name], capture_output=True,
                           timeout=60)
            procs = json.loads(Path(tmp.name).read_text()).get("processes") or []
        return round(procs[0]["footprint"] / 2**20) if procs else None
    except Exception:  # noqa: BLE001
        return None


def rss_mb(pid):
    try:
        return round(int(subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
                         .stdout.strip()) / 1024)
    except ValueError:
        return None


class MemSampler(threading.Thread):
    def __init__(self, pid, every=0.5):
        super().__init__(daemon=True)
        self.pid, self.every, self.peak_rss, self.stop = pid, every, 0, threading.Event()

    def run(self):
        while not self.stop.is_set():
            self.peak_rss = max(self.peak_rss, rss_mb(self.pid) or 0)
            time.sleep(self.every)


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--transcripts", default=str(HERE / "transcripts"))
    ap.add_argument("--glob", default="*.txt")
    ap.add_argument("--schema", choices=["auto", "pl", "en"], default="auto",
                    help="auto: schema_pl.json for pl_* transcripts, schema_en.json for en_*")
    ap.add_argument("--questions", default=None, help="comma-separated subset of schema questions")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--pid", type=int, default=None, help="basal-serve PID: sample RSS and physical footprint")
    ap.add_argument("--label", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    schemas = {k: json.loads((HERE / f"schema_{k}.json").read_text()) for k in ("pl", "en")}
    if a.questions:
        keep = a.questions.split(",")
        schemas = {k: {q: v for q, v in s.items() if q in keep} for k, s in schemas.items()}
    files = sorted(Path(a.transcripts).glob(a.glob))
    client = httpx.Client(timeout=300)
    models = client.get(f"{a.url}/v1/models").json()

    def ask(path):
        lang = path.name[:2] if a.schema == "auto" else a.schema
        body = {"state": path.read_text().strip(), "questions": schemas[lang]}
        t0 = time.perf_counter()
        r = client.post(f"{a.url}/v1/systemone", json=body)
        dt = time.perf_counter() - t0
        r.raise_for_status()
        return r.json(), dt

    for k in range(a.warmup):
        ask(files[k % len(files)])
    sampler = None
    if a.pid:
        sampler = MemSampler(a.pid); sampler.start()

    rows, lat_all = [], []
    for f in files:
        lats, srv = [], []
        for _ in range(a.repeats):
            resp, dt = ask(f)
            lats.append(dt); srv.append(resp["usage"]["latency_ms"] / 1000)
        lat_all += lats
        ans = resp["answers"]
        label, exp_type = expected(f.stem)
        row = {"id": f.stem, "label": label, "expected_type": exp_type, "input_tokens": resp["usage"]["input_tokens"],
               "latency_p50_s": round(statistics.median(lats), 3), "server_latency_p50_s": round(statistics.median(srv), 3)}
        for q in ("money", "secrecy", "authority", "urgency"):
            if q in ans:
                row[q] = round(ans[q]["noul"], 3)
        if "scam_type" in ans:
            row["scam_type"] = ans["scam_type"]["choice"]
            row["scam_type_conf"] = round(ans["scam_type"]["confidence"], 3)
        if "risk" in ans:
            row["risk_0_100"] = round(ans["risk"]["score"] / 3 * 100)
            row["risk_not_low"] = round(100 * (1 - ans["risk"]["probabilities"]["low"]))
            row["risk_probs"] = {k: round(v, 3) for k, v in ans["risk"]["probabilities"].items()}
        rows.append(row)
        print(f"{f.stem:28s} tok {row['input_tokens']:5d}  {row['latency_p50_s']:6.2f}s  "
              + "  ".join(f"{q}={row[q]:.2f}" for q in ("money", "secrecy", "authority", "urgency") if q in row)
              + (f"  type={row['scam_type']}({row['scam_type_conf']:.2f})" if "scam_type" in row else "")
              + (f"  risk={row['risk_0_100']} notlow={row['risk_not_low']}" if "risk_0_100" in row else ""),
              flush=True)

    summary = {"model": models, "schema": a.schema, "questions": list(next(iter(schemas.values()))),
               "requests_timed": len(lat_all), "latency_p50_s": round(statistics.median(lat_all), 3),
               "latency_p95_s": round(pct(lat_all, 95), 3), "latency_max_s": round(max(lat_all), 3),
               "mean_input_tokens": round(statistics.mean(r["input_tokens"] for r in rows))}
    if any("risk_0_100" in r for r in rows):
        tp = sum(r["label"] == "scam" and r["risk_0_100"] >= 50 for r in rows)
        fp = sum(r["label"] == "normal" and r["risk_0_100"] >= 50 for r in rows)
        summary.update(scams=sum(r["label"] == "scam" for r in rows), scams_flagged_ge50=tp,
                       normals=sum(r["label"] == "normal" for r in rows), normals_flagged_ge50=fp,
                       scams_ge80=sum(r["label"] == "scam" and r["risk_0_100"] >= 80 for r in rows),
                       normals_ge80=sum(r["label"] == "normal" and r["risk_0_100"] >= 80 for r in rows),
                       min_risk_not_low_scam=min(r["risk_not_low"] for r in rows if r["label"] == "scam"),
                       max_risk_not_low_normal=max(r["risk_not_low"] for r in rows if r["label"] == "normal"))
    if "scam_type" in rows[0]:
        summary["scam_type_correct"] = sum(r["scam_type"] == r["expected_type"] for r in rows)
    if sampler:
        sampler.stop.set(); sampler.join()
        summary["server_peak_rss_mb"] = sampler.peak_rss
        summary["server_footprint_mb_after"] = footprint_mb(a.pid)
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps({"label": a.label, "summary": summary, "rows": rows}, ensure_ascii=False,
                                          indent=1) + "\n")
        print("wrote", a.out)


if __name__ == "__main__":
    main()
