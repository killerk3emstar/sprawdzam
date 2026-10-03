"""Generate the voice prompts locally with macOS `say` and ffmpeg.

Texts come from `app/prompts.py` (VOICE_PROMPTS). Output: raw G.711 mu-law, 8 kHz, mono, band-
limited like a phone line, in `<DATA_DIR>/prompts/<name>_<lang>.ulaw` (default
`data/prompts/`). The audio is NOT committed (Apple voice licensing); every machine generates
its own copy. Usage (from `server/`):

    scripts/make_prompts.sh                      # Zosia (pl) and Samantha (en)
    scripts/make_prompts.sh --voice-pl Zosia --rate 170 --out /tmp/prompts
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.prompts import VOICE_PROMPTS  # noqa: E402


def main() -> int:
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=data_dir / "prompts")
    parser.add_argument("--voice-pl", default="Zosia")
    parser.add_argument("--voice-en", default="Samantha")
    parser.add_argument("--rate", type=int, default=165, help="words per minute for `say`")
    args = parser.parse_args()

    missing = [tool for tool in ("say", "ffmpeg") if shutil.which(tool) is None]
    if missing:
        print(
            f"error: missing {', '.join(missing)} (macOS `say` and `brew install ffmpeg`)",
            file=sys.stderr,
        )
        return 1
    voices = {"pl": args.voice_pl, "en": args.voice_en}
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, texts in VOICE_PROMPTS.items():
            for lang, text in texts.items():
                aiff = Path(tmp) / f"{name}_{lang}.aiff"
                target = args.out / f"{name}_{lang}.ulaw"
                subprocess.run(
                    ["say", "-v", voices[lang], "-r", str(args.rate), "-o", str(aiff), text],
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
                seconds = target.stat().st_size / 8000
                print(f"{target}  {seconds:.1f} s  ({voices[lang]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
