"""Decision-model interface (basal-1; Clef-Flash could implement the same protocol).

A client sends the speaker-labelled transcript window to the model server and maps the
answer into the *normalised* mapping validated by `DecisionResult`:

    {"risk": 0-100, "scam_type": "none" | "grandchild" | "police" | "bank" | "other",
     "money": 0-1 | None, "secrecy": 0-1 | None, "authority": 0-1 | None, "urgency": 0-1 | None}

The four signal probabilities are only present for a *full* request (`DecisionRequest.full`);
quick requests ask for `risk` and `scam_type` only. The engine validates whatever the client
returns, so a buggy client or an odd model answer can only cause a fallback to the rules,
never a crash or an out-of-range score.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.config import Lang
from app.risk.models import ScamType

SIGNALS = ("money", "secrecy", "authority", "urgency")

Probability = float | None


class DecisionBackendError(Exception):
    """Transport or protocol problem (timeout, HTTP error, 422)."""


class MalformedDecision(DecisionBackendError):
    """The server answered, but not in the expected shape."""


@dataclass(frozen=True)
class DecisionRequest:
    call_id: str
    lang: Lang
    # Speaker-labelled transcript window ("Dzwoniący: ...\nSenior: ..."). RAM only.
    state: str
    # False: risk + scam_type (every evaluation). True: all six questions (once per call).
    full: bool = False


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    risk: float = Field(ge=0, le=100, allow_inf_nan=False)
    scam_type: ScamType = ScamType.NONE
    money: Probability = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    secrecy: Probability = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    authority: Probability = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    urgency: Probability = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @property
    def has_signals(self) -> bool:
        return all(getattr(self, name) is not None for name in SIGNALS)


@runtime_checkable
class DecisionBackend(Protocol):
    name: str

    async def assess(self, request: DecisionRequest) -> Mapping[str, Any]:
        """Return the normalised mapping described in the module docstring."""
        ...
