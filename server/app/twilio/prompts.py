"""Voice prompts played by Twilio <Say>, in Polish and English."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Lang


@dataclass(frozen=True)
class Voice:
    language: str  # BCP-47 tag for <Say language=...>
    voice: str  # Twilio <Say voice=...> (Amazon Polly voices)


VOICES: dict[Lang, Voice] = {
    "pl": Voice(language="pl-PL", voice="Polly.Ewa"),
    "en": Voice(language="en-US", voice="Polly.Joanna"),
}

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

PROTECTION_UNAVAILABLE: dict[Lang, str] = {
    "pl": "Usługa ochrony połączeń jest chwilowo niedostępna. Proszę zadzwonić później.",
    "en": "The call protection service is temporarily unavailable. Please call again later.",
}
