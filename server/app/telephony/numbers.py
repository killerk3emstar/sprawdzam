"""Phone number helpers (E.164 validation and masking for logs)."""

from __future__ import annotations

import re

E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def is_e164(number: str) -> bool:
    return bool(E164_RE.fullmatch(number))


def parse_number_list(raw: str) -> frozenset[str]:
    """Parse a comma-separated list of E.164 numbers. Raises ValueError on a bad entry."""
    numbers = set()
    for item in raw.split(","):
        number = item.strip().replace(" ", "")
        if not number:
            continue
        if not is_e164(number):
            raise ValueError(f"not an E.164 number: entry #{len(numbers) + 1}")
        numbers.add(number)
    return frozenset(numbers)


def mask_number(number: str) -> str:
    """Keep the country prefix and the last two digits, e.g. '+48*******89'."""
    if len(number) <= 5:
        return "*" * len(number)
    return number[:3] + "*" * (len(number) - 5) + number[-2:]


_COUNTRY_CODES = (
    "1",
    "7",
    "20",
    "27",
    "30",
    "31",
    "32",
    "33",
    "34",
    "36",
    "39",
    "40",
    "41",
    "43",
    "44",
    "45",
    "46",
    "47",
    "48",
    "49",
)


def mask_caller(number: str) -> str:
    """Display form for the senior's app, e.g. '+48 *** *** 123'; 'unknown' if hidden."""
    number = number.strip().replace(" ", "")
    if not is_e164(number):
        return "unknown"
    digits = number[1:]
    country = next((c for c in _COUNTRY_CODES if digits.startswith(c)), digits[:2])
    return f"+{country} *** *** {digits[-3:]}"
