"""Texts of the voice prompts played to the caller, in Polish and English."""

from __future__ import annotations

from app.config import Lang

PROTECTION_NOTICE: dict[Lang, str] = {
    "pl": (
        "To połączenie jest chronione przez usługę Sprawdzam. Rozmowa jest na bieżąco "
        "sprawdzana pod kątem oszustw i nie jest nagrywana. Proszę czekać na połączenie."
    ),
    "en": (
        "This call is protected by the Second Ear service. The conversation is checked for "
        "fraud in real time and is not recorded. Please hold while we connect you."
    ),
}

# Fail-open: when protection is unavailable (no senior app connected, all call slots busy)
# the call is meant to go through to the senior unprotected, never to be refused.
PROTECTION_UNAVAILABLE: dict[Lang, str] = {
    "pl": "Usługa ochrony jest chwilowo niedostępna. Łączę bez ochrony.",
    "en": "The protection service is temporarily unavailable. Connecting you without protection.",
}
# Used only when there is no number to connect to (SENIOR_NUMBER unset, or dry-run): neutral,
# no "call again later".
PROTECTION_UNAVAILABLE_NO_ROUTE: dict[Lang, str] = {
    "pl": "Usługa ochrony jest chwilowo niedostępna.",
    "en": "The protection service is temporarily unavailable.",
}

# Pre-recorded voice prompts played through the media stream (generated locally by
# scripts/make_prompts.sh into DATA_DIR/prompts/<name>_<lang>.ulaw; not committed).
VOICE_PROMPTS: dict[str, dict[Lang, str]] = {
    # To the senior (app channel) when the risk reaches the warning level.
    "warning": {
        "pl": (
            "Uwaga. Ta rozmowa może być próbą oszustwa. Nie przekazuj pieniędzy ani kodów "
            "BLIK i nie podawaj swoich danych."
        ),
        "en": (
            "Warning. This call may be a scam. Do not hand over money or codes, and do not "
            "share your personal details."
        ),
    },
    # To the caller (and the senior) before the family-password check.
    "password": {
        "pl": "Ze względów bezpieczeństwa proszę podać hasło rodzinne na klawiaturze telefonu.",
        "en": "For security reasons, please enter the family password on your phone keypad.",
    },
    # To the caller right before a blocked call is ended.
    "blocked": {
        "pl": "Połączenie zostało zakończone przez usługę ochrony Sprawdzam.",
        "en": "This call has been ended by the Second Ear protection service.",
    },
}
