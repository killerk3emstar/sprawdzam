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
