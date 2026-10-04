"""Trusted-person alert sent by the senior's own phone (protocol v0 extension).

After a call ends with `scam_blocked` the backend asks the senior app, on its control
channel, to text the trusted person (`alert_trusted`). The text is composed here so every
client sends the same wording:

* plain ASCII (no Polish diacritics: a GSM-7 SMS stays one 160-character segment), no links,
  under 160 characters;
* scam pattern and the main warning sign mapped from `scamType` / `reasons`, with a generic
  fallback.

The text never contains transcript content or the caller's number.
"""

from __future__ import annotations

import unicodedata

from app.config import Lang

MAX_SMS_CHARS = 159

# How the PL text refers to the protected person. One constant so the demo wording
# ("babcia" = grandma) can be changed in one place; the sentence uses feminine forms.
SENIOR_PL = "babcia"

_BRAND: dict[Lang, str] = {"pl": "Sprawdzam", "en": "Second Ear"}

_SCAM_PHRASES: dict[Lang, dict[str, str]] = {
    "pl": {
        "police": "falszywy policjant",
        "grandchild": "metoda na wnuczka",
        "bank": "falszywy pracownik banku",
        "other": "proba oszustwa",
    },
    "en": {
        "police": "fake police officer",
        "grandchild": "relative in trouble scam",
        "bank": "fake bank employee",
        "other": "likely fraud",
    },
}

# Main warning sign, in priority order (the first present reason is used).
_REASON_ORDER = ("money", "secrecy", "authority", "urgency")
_REASON_PHRASES: dict[Lang, dict[str, str]] = {
    "pl": {
        "money": "prosba o pieniadze",
        "secrecy": "prosba o zachowanie tajemnicy",
        "authority": "podszywanie sie pod urzad",
        "urgency": "presja czasu",
    },
    "en": {
        "money": "asked for money",
        "secrecy": "asked to keep it secret",
        "authority": "posed as an official",
        "urgency": "pressure to act now",
    },
}
# Fake police officers typically collect cash through a "courier".
_MONEY_BY_SCAM: dict[Lang, dict[str, str]] = {
    "pl": {"police": "prosba o gotowke"},
    "en": {"police": "asked for cash"},
}


def _ascii(text: str) -> str:
    text = text.replace("ł", "l").replace("Ł", "L")
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def _sentence(lang: Lang, details: list[str]) -> str:
    inner = f" ({', '.join(details)})" if details else ""
    if lang == "pl":
        return f"{_BRAND['pl']}: {SENIOR_PL} mogla rozmawiac z oszustem{inner}. Zadzwon do niej."
    return f"{_BRAND['en']}: your relative may have talked to a scammer{inner}. Please call them."


def compose_alert_text(scam_type: str, reasons: list[str], lang: Lang) -> str:
    lang = lang if lang in _BRAND else "en"
    details: list[str] = []
    scam = _SCAM_PHRASES[lang].get(scam_type)
    if scam:
        details.append(scam)
    main = next((r for r in _REASON_ORDER if r in reasons), None)
    if main is not None:
        phrase = _MONEY_BY_SCAM[lang].get(scam_type) if main == "money" else None
        details.append(phrase or _REASON_PHRASES[lang][main])
    # Drop details until it fits (the generic sentence always does).
    while True:
        text = _ascii(_sentence(lang, details))
        if len(text) <= MAX_SMS_CHARS or not details:
            return text
        details.pop()
