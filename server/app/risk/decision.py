"""Decision-model interface (basal-1 / Clef-Flash).

The real HTTP clients come later. A client sends the speaker-labelled transcript window and
the question schema below to the model server and maps the answer into the *normalised*
mapping validated by `DecisionResult`:

    {"risk": 0-100, "money": bool, "secrecy": bool, "authority": bool, "urgency": bool,
     "scam_type": "none" | "grandchild" | "police" | "bank" | "other"}

The engine validates whatever the client returns, so a buggy client or an odd model answer
can only cause a fallback to the rules, never a crash or an out-of-range score.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.config import Lang
from app.risk.models import ScamType


class DecisionBackendError(Exception):
    """Raised by decision clients for transport or protocol problems."""


@dataclass(frozen=True)
class DecisionRequest:
    call_id: str
    lang: Lang
    # Speaker-labelled transcript window, e.g. "caller: ...\nsenior: ...". RAM only.
    state: str


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    risk: float = Field(ge=0, le=100, allow_inf_nan=False)
    money: bool = False
    secrecy: bool = False
    authority: bool = False
    urgency: bool = False
    scam_type: ScamType = ScamType.NONE


@runtime_checkable
class DecisionBackend(Protocol):
    name: str

    async def assess(self, request: DecisionRequest) -> Mapping[str, Any]:
        """Return the normalised mapping described in the module docstring."""
        ...


# Question schema for basal-1 `POST /v1/systemone` (draft from CLAUDE.md, to be tuned).
BASAL_QUESTIONS: dict[str, dict[str, Any]] = {
    "money": {
        "type": "noul",
        "instructions": "Does the caller ask for money, a bank transfer, cash handover "
        "or a BLIK code?",
    },
    "secrecy": {
        "type": "noul",
        "instructions": "Does the caller ask to keep the call secret from family or the bank?",
    },
    "authority": {
        "type": "noul",
        "instructions": "Does the caller claim to be police, a bank, a prosecutor or another "
        "authority?",
    },
    "urgency": {
        "type": "noul",
        "instructions": "Does the caller pressure the person to act immediately?",
    },
    "scam_type": {
        "type": "choice",
        "instructions": "Which scam pattern fits best?",
        "criteria": {
            "none": "Normal conversation",
            "grandchild": "Relative in trouble needs money",
            "police": "Fake police officer or prosecutor",
            "bank": "Fake bank employee, account at risk",
            "other": "Another fraud pattern",
        },
    },
    "risk": {
        "type": "score",
        "instructions": "How likely is this call a scam?",
        "criteria": {
            "low": "No signs",
            "medium": "Some warning signs",
            "high": "Clear scam pattern",
            "critical": "Money is about to be handed over",
        },
    },
}

# Suggested mapping from the "risk" score label to 0-100 for the basal client.
RISK_LABEL_TO_SCORE: dict[str, int] = {"low": 10, "medium": 55, "high": 85, "critical": 100}
