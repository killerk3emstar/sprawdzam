"""Senior's device settings (protocol v0 `settings`), kept in RAM only.

Phone numbers and names are personal data: they are never logged (counts only) and are lost
when the backend restarts; the app sends its settings again after every reconnect.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.config import Lang
from app.logging_setup import log_event
from app.relay.protocol import SettingsMessage
from app.telephony.numbers import is_e164

logger = logging.getLogger(__name__)


class InvalidSettings(ValueError):
    pass


def normalise_number(raw: str) -> str:
    return raw.strip().replace(" ", "").replace("-", "")


@dataclass(frozen=True)
class DeviceSettings:
    lang: Lang
    trusted_name: str = ""
    trusted_number: str = ""
    whitelist: frozenset[str] = field(default_factory=frozenset)
    ignored: int = 0  # whitelist entries that were not valid E.164 numbers

    @classmethod
    def from_message(cls, message: SettingsMessage) -> DeviceSettings:
        trusted_name = trusted_number = ""
        if message.trustedPerson is not None:
            trusted_number = normalise_number(message.trustedPerson.number)
            if not is_e164(trusted_number):
                raise InvalidSettings("trustedPerson.number is not an E.164 number")
            trusted_name = message.trustedPerson.name.strip()
        valid = {n for n in map(normalise_number, message.whitelist) if is_e164(n)}
        ignored = len({normalise_number(n) for n in message.whitelist}) - len(valid)
        return cls(message.lang, trusted_name, trusted_number, frozenset(valid), ignored)


def choose_trusted_number(
    device: DeviceSettings | None, fallback: str, allowlist: frozenset[str]
) -> str:
    """The app's trusted person if allowed by OUTBOUND_ALLOWLIST (a compromised app must not
    make us call arbitrary numbers), otherwise the configured TRUSTED_PERSON_NUMBER."""
    if device is not None and device.trusted_number:
        if device.trusted_number in allowlist:
            return device.trusted_number
        log_event(
            logger,
            logging.WARNING,
            "trusted_person_not_allowlisted",
            source="app_settings",
            fallback_configured=bool(fallback),
        )
    return fallback
