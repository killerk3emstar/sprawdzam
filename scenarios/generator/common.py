"""Shared helpers for the scenario generator: slot filling and Whisper-style noise.

Every random choice goes through one `random.Random` instance per call, seeded from the call id,
so `generate.py` always produces the same file.
"""

from __future__ import annotations

import random
import re

C, S = "caller", "senior"


class Slots(dict):
    """format_map() dict that leaves unknown {placeholders} untouched."""

    def __missing__(self, key):
        return "{" + key + "}"


def fill(text: str, slots: dict) -> str:
    return text.format_map(Slots(slots))


def one(r: random.Random, options):
    """Pick one option; an option may itself be a list of alternatives (nested variants)."""
    x = r.choice(options)
    while isinstance(x, list):
        x = r.choice(x)
    return x


def maybe(r: random.Random, p: float, options) -> list:
    """[one(options)] with probability p, otherwise []."""
    return [one(r, options)] if r.random() < p else []


# --------------------------------------------------------------------------------------------- noise
# Plausible speech-recognition confusions on 8 kHz phone audio (several observed in our Whisper bench:
# "przeleję" -> "przyleję", "w ciąży" -> "w ciurze", "dwieście złotych" -> "200 zł").
CONFUSIONS = {
    "pl": [
        (r"\bprzeleję\b", ["przyleję"]),
        (r"\bciąży\b", ["ciurze"]),
        (r"\bblik\b", ["blig", "blick", "blika"]),
        (r"\bkod blik\b", ["kot blik", "kod bliki"]),
        (r"\bkaucj", ["kałcj", "kaucj"]),
        (r"\bkomendy\b", ["komedii", "komendę"]),
        (r"\baspirant\b", ["aspiran", "a spirant"]),
        (r"\bprokurator\b", ["prokurato", "prokuratur"]),
        (r"\bwnuczek\b", ["wnuczę", "wnuczka"]),
        (r"\bgotówkę\b", ["gotówki", "gotowe"]),
        (r"\bkurier\b", ["kurie", "kurii"]),
        (r"\bmecenas\b", ["mecenat", "me cenas"]),
        (r"\bnatychmiast\b", ["natychmiać", "na tychmiast"]),
        (r"\bprzelew\b", ["przelef", "przelewu"]),
        (r"\bkonto\b", ["kąto", "konta"]),
        (r"\bbabciu\b", ["babcie", "babciu no"]),
        (r"\bdziadku\b", ["dziadkuu", "dziadek"]),
        (r"\bpolicji\b", ["polityki", "policję"]),
        (r"\bkryptowaluty\b", ["krypto waluty", "kryptowalut"]),
        (r"\bpieniądze\b", ["pieniądz", "pieniążki"]),
        (r"\bnikomu\b", ["nikogo", "ni komu"]),
        (r"\bproszę\b", ["prosze", "pszę"]),
        (r"\bdzień dobry\b", ["dzień do bry", "dobry"]),
        (r"\bzłotych\b", ["zł", "złoty"]),
        (r"\bbank\b", ["bang", "banku"]),
        (r"\bprzychodni\b", ["przychodnie", "przy chodni"]),
        (r"\brecepta\b", ["recepty", "recepcja"]),
    ],
    "en": [
        (r"\bbail\b", ["bale", "bell"]),
        (r"\bgift cards\b", ["gift guards", "gift card"]),
        (r"\bwire\b", ["why are", "wired"]),
        (r"\bwarrant\b", ["warren", "warrants"]),
        (r"\bbitcoin\b", ["big coin", "bit coin"]),
        (r"\baccount\b", ["a count", "accounts"]),
        (r"\bPIN\b", ["pin", "pen"]),
        (r"\bgrandma\b", ["grandmama", "grandma uh"]),
        (r"\bofficer\b", ["office", "offer sir"]),
        (r"\bprescription\b", ["perscription", "subscription"]),
        (r"\bverification\b", ["verify cation", "verification of"]),
        (r"\blawyer\b", ["lower", "layer"]),
        (r"\bpharmacy\b", ["farmacy", "pharmacies"]),
        (r"\bcourier\b", ["career", "currier"]),
        (r"\bimmediately\b", ["immediate", "mediately"]),
        (r"\bdeputy\b", ["the puppy", "deputy uh"]),
        (r"\bcrypto\b", ["cripto", "krypto"]),
        (r"\bsecurity\b", ["security uh", "secure tea"]),
    ],
}
FILLERS = {"pl": ["no", "yyy", "eee", "mhm", "znaczy", "no więc", "tak"],
           "en": ["uh", "um", "well", "so", "yeah", "okay"]}


def whisperify(text: str, lang: str, r: random.Random, noise: float = 1.0) -> str:
    """Make a clean sentence look like Whisper output on phone audio.

    Lower-cases most turns, drops some punctuation, injects occasional confusions, dropped or
    doubled words and fillers. `noise` scales the error probabilities (0 = only casing/punctuation).
    """
    out = text
    # recognition confusions (keywords included: rules and model must cope with them)
    for pattern, repl in CONFUSIONS[lang]:
        if re.search(pattern, out, flags=re.I) and r.random() < 0.10 * noise:
            out = re.sub(pattern, r.choice(repl), out, count=1, flags=re.I)
    words = out.split()
    if len(words) > 6 and r.random() < 0.07 * noise:  # dropped word
        del words[r.randrange(1, len(words) - 1)]
    if len(words) > 4 and r.random() < 0.04 * noise:  # doubled word ("to to", "the the")
        k = r.randrange(0, len(words) - 1)
        words.insert(k, re.sub(r"[^\w]", "", words[k]) or words[k])
    if r.random() < 0.08 * noise:  # leading filler
        words.insert(0, r.choice(FILLERS[lang]) + ("," if r.random() < 0.3 else ""))
    out = " ".join(words)
    # casing and punctuation: Whisper on short phone chunks is inconsistent
    style = r.random()
    if style < 0.65:
        out = out.lower()
        if lang == "en":
            out = re.sub(r"\bi\b", "I", out) if r.random() < 0.5 else out
    if style < 0.12:
        out = re.sub(r"[,.!?;:]", "", out)
    else:
        out = re.sub(r",", lambda m: "," if r.random() < 0.5 else "", out)
        out = re.sub(r"!", lambda m: "." if r.random() < 0.6 else "!", out)
        if r.random() < 0.35:
            out = out.rstrip(".")
    return re.sub(r"\s+", " ", out).strip()
