"""Render the sample caller clips for /dev/caller with macOS `say` and ffmpeg.

Texts: `scripts/samples/*.txt` (caller-side monologues from the model bench, our own
material, plus the six live-demo scripts: police, grandchild and a normal call in PL and
EN). Sentences are separated by `say` silences (`--pause-ms`) so the backend's pause-based
segmenter cuts 3-8 s speech segments, as with a real caller. Output: raw G.711 mu-law, 8 kHz, mono, phone band-pass, in
`<DATA_DIR>/samples/<name>.ulaw` (default `data/samples/`). The audio is NOT committed (Apple
voice licensing). Files starting with `pl_` use the Polish voice, `en_scam_police` the male
English voice, the other `en_` files the female English one.

    scripts/make_samples.sh                 # Zosia (pl), Samantha and Daniel (en)
    scripts/make_samples.sh --only pl_scam_police
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SENTENCE_END = re.compile(r"([.!?])\s+")


def with_pauses(text: str, pause_ms: int) -> str:
    """Insert `say` silence commands between sentences."""
    text = SENTENCE_END.sub(rf"\1 [[slnc {pause_ms}]] ", text.strip())
    return text


def main() -> int:
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--texts", type=Path, default=HERE / "samples")
    parser.add_argument("--out", type=Path, default=data_dir / "samples")
    parser.add_argument("--voice-pl", default="Zosia")
    parser.add_argument("--voice-en", default="Samantha")
    parser.add_argument("--voice-en-male", default="Daniel", help="voice for en_scam_police")
    parser.add_argument("--rate", type=int, default=170, help="words per minute for `say`")
    parser.add_argument("--pause-ms", type=int, default=700, help="silence between sentences")
    parser.add_argument("--only", nargs="*", help="render only these names (file stems)")
    args = parser.parse_args()

    missing = [tool for tool in ("say", "ffmpeg") if shutil.which(tool) is None]
    if missing:
        print(
            f"error: missing {', '.join(missing)} (macOS `say` and `brew install ffmpeg`)",
            file=sys.stderr,
        )
        return 1
    texts = sorted(args.texts.glob("*.txt"))
    if args.only:
        texts = [t for t in texts if t.stem in args.only]
    if not texts:
        print(f"error: no *.txt in {args.texts}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for text in texts:
            name = text.stem
            if name.startswith("pl_"):
                voice = args.voice_pl
            elif name == "en_scam_police":
                voice = args.voice_en_male
            else:
                voice = args.voice_en
            aiff = Path(tmp) / f"{name}.aiff"
            script = Path(tmp) / f"{name}.txt"
            script.write_text(with_pauses(text.read_text(encoding="utf-8"), args.pause_ms))
            target = args.out / f"{name}.ulaw"
            subprocess.run(
                ["say", "-v", voice, "-r", str(args.rate), "-o", str(aiff), "-f", str(script)],
                check=True,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(aiff),
                    "-af",
                    "highpass=f=300,lowpass=f=3400",
                    "-ar",
                    "8000",
                    "-ac",
                    "1",
                    "-f",
                    "mulaw",
                    str(target),
                ],
                check=True,
            )
            print(f"{target}  {target.stat().st_size / 8000:.1f} s  ({voice})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
