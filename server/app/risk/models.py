"""Shared types for the risk engine."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class Category(StrEnum):
    """Warning-sign categories (same names as the questions in the basal-1 schema)."""

    MONEY = "money"
    SECRECY = "secrecy"
    AUTHORITY = "authority"
    URGENCY = "urgency"


class ScamType(StrEnum):
    NONE = "none"
    GRANDCHILD = "grandchild"
    POLICE = "police"
    BANK = "bank"
    OTHER = "other"


class Action(StrEnum):
    NONE = "none"
    WARN = "warn"
    VERIFY_THEN_HANGUP = "verify_family_password_then_hangup"


class ActionLevel(IntEnum):
    """Ordering of actions; the engine only ever escalates."""

    NONE = 0
    WARN = 1
    VERIFY_THEN_HANGUP = 2

    @classmethod
    def of(cls, action: Action) -> ActionLevel:
        return cls[action.name]
