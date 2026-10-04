"""Trusted-person alert sent by the senior's own phone (protocol v0 extension).

After a call ends with `scam_blocked` the backend asks the senior app, on its control
channel, to text the trusted person (`alert_trusted`). The text is composed here so every
client sends the same wording:

* plain ASCII (no Polish diacritics: a GSM-7 SMS stays one 160-character segment), no links,
  at most 159 characters;
* local time of the alert (Europe/Warsaw, HH:MM), the scam pattern (`scamType`), the concrete
  money ask from the keyword rules (BLIK, cash, transfer...) or else the main warning sign
  (`reasons`), and the last three digits of the caller's number; generic fallback;
* when too long, details are dropped in this order: generic warning sign, caller digits,
  money ask, scam pattern (the time and the generic sentence always fit).

The text never contains transcript content or the caller's full number.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Lang

MAX_SMS_CHARS = 159
LOCAL_TZ = ZoneInfo("Europe/Warsaw")

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
# Concrete money ask found by the keyword rules (`RulesResult.money_ask`).
_MONEY_ASK_PHRASES: dict[Lang, dict[str, str]] = {
    "pl": {
        "blik": "prosba o kod BLIK",
        "safe_account": "przelew na bezpieczne konto",
        "transfer": "prosba o przelew",
        "credentials": "prosba o kody do banku",
        "cash": "prosba o gotowke",
        "crypto": "prosba o kryptowaluty",
        "gift_card": "prosba o karty podarunkowe",
    },
    "en": {
        "blik": "asked for a BLIK code",
        "safe_account": "transfer to a safe account",
        "transfer": "asked for a transfer",
        "credentials": "asked for bank codes",
        "cash": "asked for cash",
        "crypto": "asked for crypto",
        "gift_card": "asked for gift cards",
    },
}
_CALLER_DIGITS = re.compile(r"(\d{3})$")


def _ascii(text: str) -> str:
    text = text.replace("ł", "l").replace("Ł", "L")
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def caller_tail(caller: str) -> str | None:
    """Last three digits of a caller number or its masked form ('+48 *** *** 123')."""
    match = _CALLER_DIGITS.search(caller.strip())
    return match.group(1) if match else None


def _sentence(lang: Lang, time: str | None, details: list[str]) -> str:
    inner = f" ({', '.join(details)})" if details else ""
    brand = f"{_BRAND[lang]} {time}" if time else _BRAND[lang]
    if lang == "pl":
        return f"{brand}: {SENIOR_PL} mogla rozmawiac z oszustem{inner}. Zadzwon do niej."
    return f"{brand}: your relative may have talked to a scammer{inner}. Please call them."


def compose_alert_text(
    scam_type: str,
    reasons: list[str],
    lang: Lang,
    *,
    at: datetime | None = None,
    caller: str = "",
    money_ask: str | None = None,
) -> str:
    """`at`: time of the alert (shown as Europe/Warsaw HH:MM; naive = already local);
    `caller`: the caller's number or masked display form; `money_ask`: a
    `RulesResult.money_ask` value."""
    lang = lang if lang in _BRAND else "en"
    time = None
    if at is not None:
        local = at.astimezone(LOCAL_TZ) if at.tzinfo is not None else at
        time = local.strftime("%H:%M")
    # (priority, text): the lowest priority is dropped first when the text is too long.
    details: list[tuple[int, str]] = []
    scam = _SCAM_PHRASES[lang].get(scam_type)
    if scam:
        details.append((4, scam))
    ask = _MONEY_ASK_PHRASES[lang].get(money_ask or "")
    if ask:
        details.append((3, ask))
    else:
        main = next((r for r in _REASON_ORDER if r in reasons), None)
        if main is not None:
            phrase = _MONEY_BY_SCAM[lang].get(scam_type) if main == "money" else None
            details.append((3, phrase) if phrase else (1, _REASON_PHRASES[lang][main]))
    digits = caller_tail(caller)
    if digits:
        details.append((2, f"nr ...{digits}" if lang == "pl" else f"from a number ending {digits}"))
    while True:
        text = _ascii(_sentence(lang, time, [d for _, d in details]))
        if len(text) <= MAX_SMS_CHARS or not details:
            return text
        details.remove(min(details, key=lambda d: d[0]))
