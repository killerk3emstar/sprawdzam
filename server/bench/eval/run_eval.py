# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Evaluate the scam-risk engine on scenarios/calls.jsonl: keyword rules, basal-1 (4.5B, 1.5B) and the
production combination max(basal, rules).

Three steps; model answers are cached in results/raw_*.jsonl so the report can be re-run offline.

    # 1. whole-transcript readings (one request per call: questions risk + scam_type)
    uv run server/bench/eval/run_eval.py collect --url http://127.0.0.1:8000 --name basal-4.5B
    uv run server/bench/eval/run_eval.py collect --url http://127.0.0.1:8001 --name basal-1.5B
    uv run server/bench/eval/run_eval.py collect --url http://127.0.0.1:8000 --name basal-4.5B --view caller

    # 2. turn-by-turn replay on a stratified subset (question: risk only)
    uv run server/bench/eval/run_eval.py progressive --url http://127.0.0.1:8000 --name basal-4.5B --subset 64

    # 3. metrics, tables and failure lists -> results/summary.json, results/per_call.csv, results/tables.md
    uv run server/bench/eval/run_eval.py report

Scores (0-100):
  rules  = RulesResult.score from rules_snapshot.py (copy of the server rules, see that file)
  basal  = 100 * (1 - P(low)) of the 4-level `risk` question ("risk_not_low")
  combo  = max(basal, rules), as in server/app/risk/engine.py combine_scores()
Thresholds: warn >= 50, hang-up >= 90 (server config RISK_WARN / RISK_HANGUP).

Views: `full` = both speakers in the state (what a two-sided transcript would give), `caller` = only the
caller's turns (what the current backend transcribes: only the inbound Twilio track).
State format = TranscriptWindow.render() of the backend: "caller: ...\\nsenior: ...".
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import rules_snapshot as rules  # noqa: E402

SCHEMAS = {k: json.loads((HERE.parent / "basal" / f"schema_{k}.json").read_text()) for k in ("pl", "en")}
RESULTS = HERE / "results"
WARN, HANGUP = 50, 90
WORDS_PER_S = 2.5  # same rough speech rate as basal/progressive.py


def load_calls(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def turns_for(call, view):
    return [t for t in call["turns"] if view == "full" or t["speaker"] == "caller"]


def render(turns):
    return "\n".join(f"{t['speaker']}: {t['text']}" for t in turns)


def plain(turns):
    return " ".join(t["text"] for t in turns)


def expected_type(call):
    """Model choices are none/grandchild/police/bank/other: investment counts as other."""
    return {"investment": "other"}.get(call["scam_type"], call["scam_type"])


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))] if xs else None


def ask(client, url, lang, state, questions):
    body = {"state": state, "questions": {q: SCHEMAS[lang][q] for q in questions}}
    t0 = time.perf_counter()
    r = client.post(f"{url}/v1/systemone", json=body)
    dt = time.perf_counter() - t0
    r.raise_for_status()
    return r.json(), dt


# ------------------------------------------------------------------------------------------ collect
def cmd_collect(a):
    calls = load_calls(a.calls)
    out = RESULTS / f"raw_{a.name}_{a.view}.jsonl"
    done = set()
    if out.exists():
        done = {json.loads(line)["id"] for line in out.read_text().splitlines() if line.strip()}
    todo = [c for c in calls if c["id"] not in done]
    client = httpx.Client(timeout=a.timeout)
    model_info = client.get(f"{a.url}/v1/models").json()["models"][0]
    print(f"{a.name} ({model_info['name']}, {model_info['mode']}): {len(todo)} to do, {len(done)} cached -> {out}")
    for c in calls[:2]:  # warm-up (kernel compilation on the first requests)
        ask(client, a.url, c["lang"], render(turns_for(c, a.view)), ["risk", "scam_type"])
    with out.open("a") as f:
        for i, c in enumerate(todo, 1):
            row = {"id": c["id"], "model": model_info["name"], "view": a.view}
            try:
                resp, dt = ask(client, a.url, c["lang"], render(turns_for(c, a.view)), ["risk", "scam_type"])
                ans = resp["answers"]
                row.update(p_risk={k: round(v, 4) for k, v in ans["risk"]["probabilities"].items()},
                           scam_type=ans["scam_type"]["choice"],
                           p_type={k: round(v, 4) for k, v in ans["scam_type"]["probabilities"].items()},
                           latency_s=round(dt, 3), server_latency_s=round(resp["usage"]["latency_ms"] / 1000, 3),
                           input_tokens=resp["usage"]["input_tokens"])
            except Exception as exc:  # noqa: BLE001 - record and continue; the report counts errors
                row["error"] = f"{type(exc).__name__}: {exc}"[:200]
            f.write(json.dumps(row) + "\n")
            f.flush()
            if i % 25 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", flush=True)


# -------------------------------------------------------------------------------------- progressive
def stratified_subset(calls, n, seed=2026):
    """Same number of calls per (lang, label), half easy / half hard where possible; deterministic."""
    r = random.Random(seed)
    groups = defaultdict(list)
    for c in calls:
        groups[(c["lang"], c["label"], c["difficulty"])].append(c)
    per_cell = max(1, n // 8)
    picked = []
    for key in sorted(groups):
        g = sorted(groups[key], key=lambda c: c["id"])
        picked += r.sample(g, min(per_cell, len(g)))
    return picked


def cmd_progressive(a):
    calls = stratified_subset(load_calls(a.calls), a.subset)
    out = RESULTS / f"progressive_{a.name}_{a.view}.jsonl"
    done = set()
    if out.exists():
        done = {json.loads(line)["id"] for line in out.read_text().splitlines() if line.strip()}
    client = httpx.Client(timeout=a.timeout)
    print(f"progressive {a.name} {a.view}: {len(calls)} calls ({len(done)} cached) -> {out}")
    ask(client, a.url, "pl", "caller: dzień dobry", ["risk"])
    with out.open("a") as f:
        for i, c in enumerate(calls, 1):
            if c["id"] in done:
                continue
            series, words, seen = [], 0, []
            for t in c["turns"]:
                words += len(t["text"].split())
                if a.view == "caller" and t["speaker"] != "caller":
                    continue
                seen.append(t)
                try:
                    resp, dt = ask(client, a.url, c["lang"], render(seen), ["risk"])
                    p_low = resp["answers"]["risk"]["probabilities"]["low"]
                    series.append({"turns": len(seen), "words": words, "basal": round(100 * (1 - p_low)),
                                   "latency_s": round(dt, 3)})
                except Exception as exc:  # noqa: BLE001
                    series.append({"turns": len(seen), "words": words, "basal": None, "error": str(exc)[:120]})
            f.write(json.dumps({"id": c["id"], "name": a.name, "view": a.view, "series": series}) + "\n")
            f.flush()
            if i % 10 == 0:
                print(f"  {i}/{len(calls)}", flush=True)


# ------------------------------------------------------------------------------------------- report
def confusion(y_true, y_pred):
    tp = sum(t and p for t, p in zip(y_true, y_pred))
    fp = sum((not t) and p for t, p in zip(y_true, y_pred))
    fn = sum(t and (not p) for t, p in zip(y_true, y_pred))
    tn = sum((not t) and (not p) for t, p in zip(y_true, y_pred))
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else 0.0
    fpr = fp / (fp + tn) if fp + tn else None
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": prec, "recall": rec, "f1": f1, "fpr": fpr, "n": len(y_true)}


def auc(scores_pos, scores_neg):
    """ROC AUC = P(score of a random scam > score of a random normal call), ties count half."""
    if not scores_pos or not scores_neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in scores_pos for n in scores_neg)
    return wins / (len(scores_pos) * len(scores_neg))


def load_raw(name, view):
    p = RESULTS / f"raw_{name}_{view}.jsonl"
    if not p.exists():
        return None
    rows = {}
    for line in p.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def f3(x):
    return "–" if x is None else f"{x:.2f}"


def build_systems(calls, view):
    """Per call: score and scam_type for each available system in this view."""
    raw = {n: load_raw(n, view) for n in ("basal-4.5B", "basal-1.5B")}
    per_call, errors, latency = {}, Counter(), defaultdict(list)
    for c in calls:
        tv = turns_for(c, view)
        t0 = time.perf_counter()
        rr = rules.score_text(plain(tv), c["lang"])
        latency["rules"].append(time.perf_counter() - t0)
        entry = {"rules": {"score": rr.score, "type": rr.scam_type.value, "cats": sorted(k.value for k in rr.categories),
                           "matched": list(rr.matched)}}
        for n, rows in raw.items():
            if rows is None:
                continue
            row = rows.get(c["id"])
            if row is None:
                errors[f"{n} missing"] += 1
                continue
            if "error" in row:
                errors[f"{n} request error"] += 1
                continue  # model failed: production would fall back to rules only; excluded from model metrics
            s = round(100 * (1 - row["p_risk"]["low"]))
            entry[n] = {"score": s, "type": row["scam_type"], "p_risk": row["p_risk"]}
            latency[n].append(row["latency_s"])
            short = n.split("-")[1]
            entry[f"max({short}, rules)"] = {"score": max(s, rr.score),
                                             "type": row["scam_type"] if row["scam_type"] != "none" else rr.scam_type.value}
        per_call[c["id"]] = entry
    systems = ["rules"] + [k for k in ("basal-4.5B", "basal-1.5B", "max(4.5B, rules)", "max(1.5B, rules)")
                           if any(k in e for e in per_call.values())]
    return per_call, systems, errors, latency


def metrics_for(calls, per_call, system, thr):
    sub = [c for c in calls if system in per_call[c["id"]]]
    y = [c["label"] == "scam" for c in sub]
    p = [per_call[c["id"]][system]["score"] >= thr for c in sub]
    return confusion(y, p)


def type_accuracy(calls, per_call, system):
    scams = [c for c in calls if c["label"] == "scam" and system in per_call[c["id"]]]
    allc = [c for c in calls if system in per_call[c["id"]]]
    ok_s = sum(per_call[c["id"]][system]["type"] == expected_type(c) for c in scams)
    ok_a = sum(per_call[c["id"]][system]["type"] == expected_type(c) for c in allc)
    return (ok_s / len(scams) if scams else None), (ok_a / len(allc) if allc else None)


def smooth_events(scores, mode):
    """First reading index (0-based) at which warn / hang-up fire under a smoothing mode."""
    warn = hang = None
    for k in range(len(scores)):
        last2 = scores[max(0, k - 1):k + 1]
        if mode == "single":
            w, h = scores[k] >= WARN, scores[k] >= HANGUP
        elif mode == "avg2":  # server ScoreSmoother: moving average of last 2 for warn, last 2 both >= for hang-up
            w = sum(last2) / len(last2) >= WARN
            h = len(last2) == 2 and min(last2) >= HANGUP
        else:  # "2row": two consecutive readings at/above the threshold
            w = len(last2) == 2 and min(last2) >= WARN
            h = len(last2) == 2 and min(last2) >= HANGUP
        if w and warn is None:
            warn = k
        if h and hang is None:
            hang = k
    return warn, hang


def progressive_report(calls_by_id, name, view):
    p = RESULTS / f"progressive_{name}_{view}.jsonl"
    if not p.exists():
        return None
    rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    out = {"n_calls": len(rows), "n_readings": sum(len(r["series"]) for r in rows), "systems": {}}
    lat = [s["latency_s"] for r in rows for s in r["series"] if s.get("latency_s")]
    out["latency_p50_s"], out["latency_p95_s"] = pct(lat, 50), pct(lat, 95)
    per_call = {}
    for r in rows:
        c = calls_by_id[r["id"]]
        tv = turns_for(c, view)
        seq = {"rules": [], name: [], "combo": []}
        for s in r["series"]:
            rs = rules.score_text(plain(tv[:s["turns"]]), c["lang"]).score
            b = s["basal"] if s["basal"] is not None else 0
            seq["rules"].append(rs)
            seq[name].append(b if s["basal"] is not None else None)
            seq["combo"].append(max(rs, b) if s["basal"] is not None else rs)
        per_call[r["id"]] = (c, r["series"], seq)
    for system in ("rules", name, "combo"):
        for mode in ("single", "avg2", "2row"):
            scam_warn, scam_hang, norm_warn, norm_hang, t_warn, turn_warn, frac_warn, t_hang = 0, 0, 0, 0, [], [], [], []
            fails, fps = [], []
            n_s = n_n = 0
            for cid, (c, series, seq) in per_call.items():
                sc = [x if x is not None else 0 for x in seq[system]]
                w, h = smooth_events(sc, mode)
                if c["label"] == "scam":
                    n_s += 1
                    if w is not None:
                        scam_warn += 1
                        t_warn.append(series[w]["words"] / WORDS_PER_S)
                        turn_warn.append(w + 1)
                        frac_warn.append((w + 1) / len(series))
                    else:
                        fails.append(cid)
                    scam_hang += h is not None
                    if h is not None:
                        t_hang.append(series[h]["words"] / WORDS_PER_S)
                else:
                    n_n += 1
                    if w is not None:
                        norm_warn += 1
                        fps.append(cid)
                    norm_hang += h is not None
            out["systems"][f"{system}|{mode}"] = {
                "scams": n_s, "scams_warned": scam_warn, "scams_hung_up": scam_hang, "normals": n_n,
                "normals_false_warn": norm_warn, "normals_false_hangup": norm_hang,
                "time_to_warn_s_median": statistics.median(t_warn) if t_warn else None,
                "time_to_warn_s_p90": pct(t_warn, 90), "time_to_hangup_s_median": statistics.median(t_hang) if t_hang else None, "readings_to_warn_median": statistics.median(turn_warn) if turn_warn else None,
                "share_of_call_elapsed_at_warn_median": statistics.median(frac_warn) if frac_warn else None,
                "scams_never_warned": fails, "normals_warned": fps}
    return out


def cmd_report(a):
    calls = load_calls(a.calls)
    by_id = {c["id"]: c for c in calls}
    summary = {"dataset": {"n": len(calls), "by_lang_label": Counter(f"{c['lang']}/{c['label']}" for c in calls),
                           "by_difficulty": Counter(f"{c['label']}/{c['difficulty']}" for c in calls)},
               "thresholds": {"warn": WARN, "hangup": HANGUP}, "views": {}}
    md = []
    for view in ("full", "caller"):
        per_call, systems, errors, latency = build_systems(calls, view)
        if view == "caller" and len(systems) == 1:
            systems = ["rules"]
        v = {"systems": {}, "model_errors": dict(errors)}
        md.append(f"\n## View: `{view}` ({'both speakers' if view == 'full' else 'caller turns only'})\n")
        if errors:
            md.append(f"Calls without a model reading (excluded from that system's metrics): {dict(errors)}\n")
        md.append("| system | n | warn ≥50: precision | recall | F1 | FPR | TP/FP/FN/TN | hang-up ≥90: precision | recall | FPR | TP/FP/FN/TN | ROC AUC | scam_type acc. (scams) | (all calls) |")
        md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for s in systems:
            mw, mh = metrics_for(calls, per_call, s, WARN), metrics_for(calls, per_call, s, HANGUP)
            pos = [per_call[c["id"]][s]["score"] for c in calls if c["label"] == "scam" and s in per_call[c["id"]]]
            neg = [per_call[c["id"]][s]["score"] for c in calls if c["label"] == "normal" and s in per_call[c["id"]]]
            ta_s, ta_a = type_accuracy(calls, per_call, s)
            v["systems"][s] = {"warn": mw, "hangup": mh, "auc": auc(pos, neg), "scam_type_acc_scams": ta_s, "scam_type_acc_all": ta_a}
            md.append(f"| {s} | {mw['n']} | {f3(mw['precision'])} | {f3(mw['recall'])} | {f3(mw['f1'])} | {f3(mw['fpr'])} | "
                      f"{mw['tp']}/{mw['fp']}/{mw['fn']}/{mw['tn']} | {f3(mh['precision'])} | {f3(mh['recall'])} | {f3(mh['fpr'])} | "
                      f"{mh['tp']}/{mh['fp']}/{mh['fn']}/{mh['tn']} | {f3(auc(pos, neg))} | {f3(ta_s)} | {f3(ta_a)} |")
        # hang-up guard variant (server config SECRECY_HANGUP_MIN: hang-up also needs secrecy or a rule hit)
        for s in [x for x in systems if x.startswith("max(")]:
            y = [c["label"] == "scam" for c in calls if s in per_call[c["id"]]]
            pr = [per_call[c["id"]][s]["score"] >= HANGUP and bool(per_call[c["id"]]["rules"]["cats"])
                  for c in calls if s in per_call[c["id"]]]
            m = confusion(y, pr)
            v["systems"][s]["hangup_with_rule_guard"] = m
            md.append(f"\nHang-up guard for `{s}` (score ≥ 90 **and** at least one keyword-rule category matched): precision {f3(m['precision'])}, "
                      f"recall {f3(m['recall'])}, FPR {f3(m['fpr'])}, TP/FP/FN/TN {m['tp']}/{m['fp']}/{m['fn']}/{m['tn']}.")
        # alternative action policies for the production combination (whole-transcript, single reading)
        if "basal-4.5B" in systems:
            ids = [c for c in calls if "basal-4.5B" in per_call[c["id"]]]
            y = [c["label"] == "scam" for c in ids]
            mod = [per_call[c["id"]]["basal-4.5B"]["score"] for c in ids]
            rul = [per_call[c["id"]]["rules"]["score"] for c in ids]
            policies = {
                "warn: max ≥ 50 (production)": [max(m, r) >= WARN for m, r in zip(mod, rul)],
                "warn: model ≥ 50 or rules ≥ 80": [m >= WARN or r >= 80 for m, r in zip(mod, rul)],
                "hang-up: max ≥ 90 (production)": [max(m, r) >= HANGUP for m, r in zip(mod, rul)],
                "hang-up: model ≥ 90 (rules can only warn)": [m >= HANGUP for m in mod],
                "hang-up: max ≥ 90 and model ≥ 50": [max(m, r) >= HANGUP and m >= WARN for m, r in zip(mod, rul)],
            }
            md.append("\n**Action policies, basal-4.5B + rules** (single whole-transcript reading; exploratory, same data):\n")
            md.append("| policy | precision | recall | FPR | TP/FP/FN/TN |")
            md.append("|---|---|---|---|---|")
            v["policies"] = {}
            for name, pred in policies.items():
                m = confusion(y, pred)
                v["policies"][name] = m
                md.append(f"| {name} | {f3(m['precision'])} | {f3(m['recall'])} | {f3(m['fpr'])} | {m['tp']}/{m['fp']}/{m['fn']}/{m['tn']} |")
        # breakdowns at warn
        md.append("\n**Breakdown at warn ≥ 50** (recall on scams / false-positive rate on normal calls):\n")
        groups = [("lang", "pl"), ("lang", "en"), ("difficulty", "easy"), ("difficulty", "hard"), ("source", "handwritten")]
        md.append("| system | " + " | ".join(f"{k}={val}: recall / FPR" for k, val in groups) + " |")
        md.append("|---|" + "---|" * len(groups))
        v["breakdown_warn"] = {}
        for s in systems:
            cells = []
            for k, val in groups:
                sub = [c for c in calls if c[k] == val]
                m = metrics_for(sub, per_call, s, WARN)
                v["breakdown_warn"].setdefault(s, {})[f"{k}={val}"] = m
                cells.append(f"{f3(m['recall'])} / {f3(m['fpr'])} (n={m['n']})")
            md.append(f"| {s} | " + " | ".join(cells) + " |")
        # per family
        fams = sorted({c["family"] for c in calls if c["source"] == "template"} | {"handwritten"})
        md.append("\n**Per family at warn ≥ 50** (scam families: share flagged = recall; normal families: share flagged = false positives):\n")
        md.append("| family | label | n | " + " | ".join(systems) + " |")
        md.append("|---|---|---|" + "---|" * len(systems))
        v["per_family"] = {}
        for fam in fams:
            for label in ("scam", "normal"):
                sub = [c for c in calls if c["family"] == fam and c["label"] == label]
                if not sub:
                    continue
                cells = []
                for s in systems:
                    ss = [c for c in sub if s in per_call[c["id"]]]
                    flagged = sum(per_call[c["id"]][s]["score"] >= WARN for c in ss)
                    v["per_family"].setdefault(f"{fam}/{label}", {})[s] = [flagged, len(ss)]
                    cells.append(f"{flagged}/{len(ss)}")
                md.append(f"| {fam} | {label} | {len(sub)} | " + " | ".join(cells) + " |")
        # threshold sweep
        md.append("\n**Threshold sweep** (recall / FPR):\n")
        thrs = [20, 30, 40, 50, 60, 70, 80, 90, 95]
        md.append("| system | " + " | ".join(f"≥{t}" for t in thrs) + " |")
        md.append("|---|" + "---|" * len(thrs))
        v["sweep"] = {}
        for s in systems:
            cells = []
            for t in thrs:
                m = metrics_for(calls, per_call, s, t)
                v["sweep"].setdefault(s, {})[t] = {"recall": m["recall"], "fpr": m["fpr"], "precision": m["precision"]}
                cells.append(f"{f3(m['recall'])} / {f3(m['fpr'])}")
            md.append(f"| {s} | " + " | ".join(cells) + " |")
        # scam-type confusion for the model
        for s in [x for x in systems if x.startswith("basal")]:
            conf = Counter((expected_type(c), per_call[c["id"]][s]["type"]) for c in calls if s in per_call[c["id"]])
            labels = ["none", "grandchild", "police", "bank", "other"]
            md.append(f"\n**scam_type confusion, {s}** (rows = expected, investment counted as other; columns = predicted):\n")
            md.append("| expected \\ predicted | " + " | ".join(labels) + " |")
            md.append("|---|" + "---|" * len(labels))
            for e in labels:
                md.append(f"| {e} | " + " | ".join(str(conf[(e, p)]) for p in labels) + " |")
            v["systems"][s]["scam_type_confusion"] = {f"{e}->{p}": n for (e, p), n in conf.items()}
        # latency
        md.append("\n**Latency per whole-transcript reading** (client side, risk + scam_type):\n")
        md.append("| system | n | p50 s | p95 s | max s |")
        md.append("|---|---|---|---|---|")
        v["latency"] = {}
        for s, xs in latency.items():
            if xs:
                v["latency"][s] = {"n": len(xs), "p50": pct(xs, 50), "p95": pct(xs, 95), "max": max(xs)}
                fmt = (lambda x: f"{x * 1000:.2f} ms") if s == "rules" else (lambda x: f"{x:.2f}")
                md.append(f"| {s} | {len(xs)} | {fmt(pct(xs, 50))} | {fmt(pct(xs, 95))} | {fmt(max(xs))} |")
        # failures of the production combination (warn)
        prod = "max(4.5B, rules)" if "max(4.5B, rules)" in systems else systems[-1]
        fn = [c for c in calls if c["label"] == "scam" and prod in per_call[c["id"]] and per_call[c["id"]][prod]["score"] < WARN]
        fp = [c for c in calls if c["label"] == "normal" and prod in per_call[c["id"]] and per_call[c["id"]][prod]["score"] >= WARN]
        fph = [c for c in calls if c["label"] == "normal" and prod in per_call[c["id"]] and per_call[c["id"]][prod]["score"] >= HANGUP]
        v["failures"] = {"system": prod, "missed_scams_warn": [c["id"] for c in fn], "false_warn": [c["id"] for c in fp],
                         "false_hangup": [c["id"] for c in fph]}

        def sc(c):
            e = per_call[c["id"]]
            parts = [f"rules {e['rules']['score']}"] + [f"{k} {e[k]['score']}" for k in ("basal-4.5B", "basal-1.5B") if k in e]
            return ", ".join(parts)

        md.append(f"\n**Missed scams at warn, `{prod}`** ({len(fn)}): " + ("; ".join(f"`{c['id']}` ({sc(c)})" for c in fn) or "none"))
        md.append(f"\n**False warnings, `{prod}`** ({len(fp)}): " + ("; ".join(f"`{c['id']}` ({sc(c)})" for c in fp) or "none"))
        md.append(f"\n**False hang-ups (single reading ≥ 90), `{prod}`** ({len(fph)}): " + ("; ".join(f"`{c['id']}` ({sc(c)})" for c in fph) or "none"))
        summary["views"][view] = v
        if view == "full":
            with (RESULTS / "per_call.csv").open("w", newline="") as f:
                w = csv.writer(f)
                cols = ["id", "lang", "label", "scam_type", "difficulty", "source", "family", "rules_score", "rules_type",
                        "basal45_score", "basal45_type", "basal15_score", "basal15_type", "combo45_score", "combo45_type"]
                w.writerow(cols)
                for c in calls:
                    e = per_call[c["id"]]
                    g = lambda k, f: e[k][f] if k in e else ""  # noqa: E731
                    w.writerow([c["id"], c["lang"], c["label"], c["scam_type"], c["difficulty"], c["source"], c["family"],
                                g("rules", "score"), g("rules", "type"), g("basal-4.5B", "score"), g("basal-4.5B", "type"),
                                g("basal-1.5B", "score"), g("basal-1.5B", "type"), g("max(4.5B, rules)", "score"),
                                g("max(4.5B, rules)", "type")])
    # progressive
    summary["progressive"] = {}
    for name in ("basal-4.5B", "basal-1.5B"):
        for view in ("full", "caller"):
            pr = progressive_report(by_id, name, view)
            if not pr:
                continue
            summary["progressive"][f"{name}|{view}"] = pr
            md.append(f"\n## Turn-by-turn replay: `{name}`, view `{view}` ({pr['n_calls']} calls, {pr['n_readings']} readings, "
                      f"risk-only latency p50 {pr['latency_p50_s']:.2f} s, p95 {pr['latency_p95_s']:.2f} s)\n")
            md.append("Subset: 8 calls per language × label × difficulty (32 scams; 32 normal calls = 16 plain chats + 16 hard negatives), "
                      "seed 2026. State after each turn = all turns so far (≈ the 60 s window); time = words so far / 2.5 words per s. "
                      "Latency measured while other replays ran on the same GPU.\n")
            md.append("Smoothing: `single` = one reading; `avg2` = server ScoreSmoother (warn when the mean of the last 2 readings ≥ 50, "
                      "hang-up when the last 2 are both ≥ 90); `2row` = warn only when 2 consecutive readings ≥ 50.\n")
            md.append("| system | smoothing | scams warned | median time to warn (s) | p90 (s) | median share of call elapsed | scams hung up | median time to hang-up (s) | normals falsely warned | normals falsely hung up |")
            md.append("|---|---|---|---|---|---|---|---|---|---|")
            for key, m in pr["systems"].items():
                sysn, mode = key.split("|")
                md.append(f"| {sysn} | {mode} | {m['scams_warned']}/{m['scams']} | {f3(m['time_to_warn_s_median'])} | {f3(m['time_to_warn_s_p90'])} | "
                          f"{f3(m['share_of_call_elapsed_at_warn_median'])} | {m['scams_hung_up']}/{m['scams']} | {f3(m['time_to_hangup_s_median'])} | {m['normals_false_warn']}/{m['normals']} | "
                          f"{m['normals_false_hangup']}/{m['normals']} |")
            for key in (f"combo|avg2", f"combo|2row"):
                m = pr["systems"][key]
                md.append(f"\n`{key}`: never warned: {', '.join('`'+x+'`' for x in m['scams_never_warned']) or 'none'}; "
                          f"normals warned: {', '.join('`'+x+'`' for x in m['normals_warned']) or 'none'}")
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n")
    (RESULTS / "tables.md").write_text("# Evaluation tables (generated by run_eval.py report)\n" + "\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\nwrote {RESULTS / 'summary.json'}, {RESULTS / 'per_call.csv'}, {RESULTS / 'tables.md'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calls", default=str(ROOT / "scenarios" / "calls.jsonl"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "progressive"):
        p = sub.add_parser(name)
        p.add_argument("--url", default="http://127.0.0.1:8000")
        p.add_argument("--name", required=True, help="label used in result file names, e.g. basal-4.5B")
        p.add_argument("--view", choices=["full", "caller"], default="full")
        p.add_argument("--timeout", type=float, default=60)
        if name == "progressive":
            p.add_argument("--subset", type=int, default=64)
    sub.add_parser("report")
    a = ap.parse_args()
    RESULTS.mkdir(exist_ok=True)
    {"collect": cmd_collect, "progressive": cmd_progressive, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
