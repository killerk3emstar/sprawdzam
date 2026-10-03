# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Latency and accuracy of a running whisper-server on phone-quality test clips.

For every clip (16 kHz mono WAV produced by make_audio.sh) it sends:
  * the whole clip once (after one warm-up request), and
  * the clip cut into fixed chunks of 2, 3 and 4 s (what the backend will send after VAD),
then reports latency (p50 / p95 / max per chunk size), WER against the TTS script and which scam keywords survived.

    uv run server/bench/stt/bench_whisper.py --url http://127.0.0.1:8080 --out server/bench/results/whisper.json
"""
import argparse
import io
import json
import re
import statistics
import time
import unicodedata
import wave
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent

# keywords the risk rules depend on (lowercase stems, matched as substrings of the normalised transcript)
KEYWORDS = {
    "pl_scam_police": ["policj", "aspirant", "wnucz", "wypadek", "kaucj", "nikomu", "gotówk", "blik", "prokurator",
                       "natychmiast"],
    "pl_scam_bank": ["bank", "kredyt", "oszczędności", "przelać", "bezpieczne konto", "aplikacj", "kod", "sms",
                     "nikim"],
    "pl_normal_family": ["mamo", "lekarz", "niedziel", "obiad", "dwieście złotych", "przeleję", "konto"],
    "en_scam_bank": ["fraud", "bank", "loan", "safe account", "do not tell", "one-time code", "card", "immediately"],
    "en_normal_family": ["grandma", "birthday", "twenty dollars", "concert", "sunday", "lunch"],
}


def norm(s):
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"[^\w\s-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def wer(ref, hyp):
    r, h = norm(ref).split(), norm(hyp).split()
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


def read_wav(path):
    with wave.open(str(path)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2, path
        return w.readframes(w.getnframes())


def to_wav(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm)
    return buf.getvalue()


def transcribe(client, url, wav_bytes, lang):
    t0 = time.perf_counter()
    r = client.post(f"{url}/inference", files={"file": ("chunk.wav", wav_bytes, "audio/wav")},
                    data={"language": lang, "response_format": "json", "temperature": "0.0",
                          "temperature_inc": "0.2"})
    dt = time.perf_counter() - t0
    r.raise_for_status()
    return r.json().get("text", "").strip(), dt


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--audio-dir", default=str(Path.home() / "models/sprawdzam/audio"))
    ap.add_argument("--chunks", default="2,3,4", help="chunk lengths in seconds")
    ap.add_argument("--label", default="large-v3-turbo")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    audio = Path(a.audio_dir)
    clips = sorted(audio.glob("*_16k.wav"))
    if not clips:
        raise SystemExit(f"no *_16k.wav in {audio}; run server/bench/stt/make_audio.sh first")
    client = httpx.Client(timeout=120)
    # warm-up (first request allocates Metal buffers)
    transcribe(client, a.url, to_wav(read_wav(clips[0])[: 16000 * 2 * 3]), "pl")

    results = {"label": a.label, "url": a.url, "clips": {}, "latency": {}}
    lat_by_chunk = {int(c): [] for c in a.chunks.split(",")}
    lat_full = []
    for clip in clips:
        name = clip.name.removesuffix("_16k.wav")
        lang = name[:2]
        ref = (HERE / "scripts" / f"{name}.txt").read_text()
        pcm = read_wav(clip)
        dur = len(pcm) / 32000
        text, dt = transcribe(client, a.url, to_wav(pcm), lang)
        lat_full.append(dt)
        entry = {"duration_s": round(dur, 2), "full": {"latency_s": round(dt, 3), "rtf": round(dt / dur, 3),
                                                       "wer": round(wer(ref, text), 3), "text": text}}
        kws = KEYWORDS.get(name, [])
        entry["full"]["keywords_missing"] = [k for k in kws if k not in norm(text)]
        for c in lat_by_chunk:
            step = c * 32000
            texts, lats = [], []
            for off in range(0, len(pcm), step):
                piece = pcm[off: off + step]
                if len(piece) < 32000 * 0.5:  # ignore a tail shorter than 0.5 s
                    continue
                t, d = transcribe(client, a.url, to_wav(piece), lang)
                texts.append(t); lats.append(d)
            lat_by_chunk[c] += lats
            joined = " ".join(texts)
            entry[f"chunks_{c}s"] = {"n": len(lats), "p50_s": round(statistics.median(lats), 3),
                                     "max_s": round(max(lats), 3), "wer": round(wer(ref, joined), 3),
                                     "keywords_missing": [k for k in kws if k not in norm(joined)], "text": joined}
        results["clips"][name] = entry
        print(f"{name:20s} {dur:5.1f}s  full {dt:5.2f}s WER {entry['full']['wer']:.2f}  "
              + "  ".join(f"{c}s: p50 {entry[f'chunks_{c}s']['p50_s']:.2f}s WER {entry[f'chunks_{c}s']['wer']:.2f}"
                          for c in lat_by_chunk)
              + f"  missing(full)={entry['full']['keywords_missing']}")
    for c, lats in lat_by_chunk.items():
        results["latency"][f"chunk_{c}s"] = {"n": len(lats), "p50_s": round(statistics.median(lats), 3),
                                             "p95_s": round(pct(lats, 95), 3), "max_s": round(max(lats), 3)}
    results["latency"]["full_clip"] = {"n": len(lat_full), "p50_s": round(statistics.median(lat_full), 3),
                                       "max_s": round(max(lat_full), 3)}
    print(json.dumps(results["latency"], indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n")
        print("wrote", a.out)


if __name__ == "__main__":
    main()
