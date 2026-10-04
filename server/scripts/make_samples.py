"""Render the sample caller clips for /dev/caller with macOS `say` and ffmpeg.

Texts: `scripts/samples/*.txt` (caller-side monologues from the model bench, our own
material). Output: raw G.711 mu-law, 8 kHz, mono, phone band-pass, in
`<DATA_DIR>/samples/<name>.ulaw` (default `data/samples/`). The audio is NOT committed (Apple
voice licensing). Files starting with `pl_` use the Polish voice, others the English one.

    scripts/make_samples.sh                 # Zosia (pl) and Samantha (en)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--texts", type=Path, default=HERE / "samples")
    parser.add_argument("--out", type=Path, default=data_dir / "samples")
    parser.add_argument("--voice-pl", default="Zosia")
    parser.add_argument("--voice-en", default="Samantha")
    parser.add_argument("--rate", type=int, default=175, help="words per minute for `say`")
    args = parser.parse_args()

    missing = [tool for tool in ("say", "ffmpeg") if shutil.which(tool) is None]
    if missing:
        print(
            f"error: missing {', '.join(missing)} (macOS `say` and `brew install ffmpeg`)",
            file=sys.stderr,
        )
        return 1
    texts = sorted(args.texts.glob("*.txt"))
    if not texts:
        print(f"error: no *.txt in {args.texts}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for text in texts:
            name = text.stem
            voice = args.voice_pl if name.startswith("pl_") else args.voice_en
            aiff = Path(tmp) / f"{name}.aiff"
            target = args.out / f"{name}.ulaw"
            subprocess.run(
                ["say", "-v", voice, "-r", str(args.rate), "-o", str(aiff), "-f", str(text)],
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
