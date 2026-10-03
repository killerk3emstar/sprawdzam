"""Keyword and phrase rules (Polish and English) for scam warning signs.

The rules are the safety net when the decision model is slow, down or wrong, so they are
deliberately conservative:

* Text is normalised first (lowercase, Polish diacritics removed, punctuation dropped), so
  "Przelać", "przelac" and "PRZELAĆ!" all match the same pattern.
* Each rule belongs to one warning-sign category (money, secrecy, authority, urgency) with a
  weak (0.5) or strong (1.0) strength, or adds "context" points (scam story elements such as
  an accident, bail or an account "at risk").
* A category counts once (the strongest match), so repeating a word does not inflate the score.
* Single words score low. Combinations score much higher through pair bonuses, because a
  scam needs several signs at once: e.g. authority + money + secrecy.

Patterns are written against the normalised text (ASCII, single spaces). Polish words are
matched by stem to cover inflection ("przelew", "przelać", "przelej", "przelał").
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import combinations
from typing import Literal

from app.config import Lang
from app.risk.models import Category, ScamType

WEAK = 0.5
STRONG = 1.0

RuleLang = Literal["pl", "en"]


@dataclass(frozen=True)
class Rule:
    id: str
    lang: RuleLang
    pattern: re.Pattern[str]
    category: Category | None = None
    strength: float = 0.0
    context_points: int = 0
    hint: ScamType | None = None


def _rule(
    rule_id: str,
    pattern: str,
    *,
    category: Category | None = None,
    strength: float = 0.0,
    context: int = 0,
    hint: ScamType | None = None,
) -> Rule:
    lang: RuleLang = "pl" if rule_id.startswith("pl.") else "en"
    if category is None and context <= 0:
        raise ValueError(f"rule {rule_id} needs a category or context points")
    return Rule(
        id=rule_id,
        lang=lang,
        pattern=re.compile(pattern),
        category=category,
        strength=strength,
        context_points=context,
        hint=hint,
    )


M, S, A, U = Category.MONEY, Category.SECRECY, Category.AUTHORITY, Category.URGENCY
G, P, B, OTH = ScamType.GRANDCHILD, ScamType.POLICE, ScamType.BANK, ScamType.OTHER

# Up to N filler words between two parts of a phrase.
_W2 = r"(?:\w+ ){0,2}"
_W3 = r"(?:\w+ ){0,3}"

RULES: tuple[Rule, ...] = (
    # ----------------------------------------------------------------- Polish: money
    _rule("pl.money.blik", r"\bblik\w*", category=M, strength=STRONG, hint=B),
    _rule("pl.money.transfer", r"\bprzel(?:ew|ac|ej|al|an)\w*", category=M, strength=STRONG),
    _rule(
        "pl.money.courier_pickup",
        rf"\bkurier\w* {_W3}(?:odbier|zabier|przyjedzie po|przyjdzie po)\w*"
        rf"|\b(?:odda|przekaz|wrecz|da)\w* {_W3}kurierowi\b"
        rf"|\b(?:pieniadz|pieniedz|gotowk)\w* {_W3}(?:\w+ )?kurier\w*",
        category=M,
        strength=STRONG,
        hint=OTH,
    ),
    _rule(
        "pl.money.safe_account",
        r"\bbezpieczn\w* (?:kont|rachun)\w*|\bkont\w* techniczn\w*",
        category=M,
        strength=STRONG,
        hint=B,
    ),
    _rule(
        "pl.money.credentials",
        r"\bkod\w* (?:z )?sms\w*|\bnumer\w* (?:\w+ )?kart\w*|\bpin(?:u|em)?\b"
        r"|\bhasl\w* do (?:banku|bankowosci|konta)\b|\bdan\w* do logowania\b|\blogin\w* i hasl\w*",
        category=M,
        strength=STRONG,
        hint=B,
    ),
    _rule(
        "pl.money.crypto_gift",
        r"\bkryptowalut\w*|\bbitcoin\w*|\b(?:kart|bon)\w* podarunkow\w*",
        category=M,
        strength=STRONG,
        hint=OTH,
    ),
    # Whisper writes numbers as digits: "30 tysięcy", "200 zł", "5 000 złotych", "2,5 tys."
    _rule(
        "pl.money.amount_digits",
        r"\b\d+(?: \d{3})*(?: \d+)? ?"
        r"(?:zl|zlotych|zlote|zloty|pln|tys|tysiecy|tysiace|tysiac|mln|k)\b",
        category=M,
        strength=WEAK,
    ),
    _rule(
        "pl.money.code_digits",
        r"\b(?:kod\w*|blik\w*)(?: [a-z]\w*){0,3} \d{3} ?\d{3}(?!\d)",
        category=M,
        strength=STRONG,
        hint=B,
    ),
    _rule("pl.money.withdraw", r"\bwyplac\w*", category=M, strength=WEAK),
    _rule("pl.money.cash", r"\bgotowk\w*", category=M, strength=WEAK),
    _rule("pl.money.money", r"\bpieni(?:adz|edz)\w*|\boszczednosc\w*", category=M, strength=WEAK),
    # ----------------------------------------------------------------- Polish: secrecy
    _rule(
        "pl.secrecy.tell_nobody",
        rf"\bnikomu {_W2}nie (?:mow|powiedz|wspomin|zdradz|informuj)\w*"
        rf"|\bnie (?:mow|powiedz|wspominaj|informuj)\w* {_W2}nikomu\b"
        r"|\bnikomu ani slowa\b",
        category=S,
        strength=STRONG,
    ),
    _rule(
        "pl.secrecy.not_family_bank",
        rf"\bnie (?:mow|powiedz|informuj|dzwon|kontaktuj)\w* {_W2}"
        r"(?:rodzin|rodzic|bank|policj)\w*",
        category=S,
        strength=STRONG,
    ),
    _rule(
        "pl.secrecy.secret_operation",
        r"\btajn\w* (?:akcj|operacj|sledztw|dochodzeni)\w*"
        r"|\btajemnic\w* (?:sledztw|panstwow|sluzbow)\w*|\bobjet\w* tajemnic\w*",
        category=S,
        strength=STRONG,
        hint=P,
    ),
    # ----------------------------------------------------------------- Polish: authority
    _rule(
        "pl.authority.claim",
        rf"\b(?:jestem|tu|mowi|z tej strony) {_W2}"
        r"(?:policj|komisarz|aspirant|funkcjonariusz|detektyw|prokurat|cbs|cba|abw)\w*",
        category=A,
        strength=STRONG,
        hint=P,
    ),
    _rule(
        "pl.authority.special",
        r"\bcbs\b|\bcba\b|\babw\b|\bcentraln\w* biur\w* (?:sledcz|antykorupc)\w*|\bprokurat\w*",
        category=A,
        strength=STRONG,
        hint=P,
    ),
    _rule(
        "pl.authority.police",
        r"\bpolicj\w*|\bkomisariat\w*|\bkomend\w*",
        category=A,
        strength=WEAK,
        hint=P,
    ),
    _rule(
        "pl.authority.officer",
        r"\b(?:komisarz|aspirant|funkcjonariusz|detektyw)\w*",
        category=A,
        strength=WEAK,
        hint=P,
    ),
    _rule(
        "pl.authority.bank_employee",
        rf"\b(?:pracownik|konsultant|doradc|specjalist)\w* {_W2}bank\w*"
        r"|\bdzial\w* bezpieczenstwa\b"
        rf"|\b(?:dzwonie|dzwonimy|jestem|tu) (?:\w+ )?z (?:\w+ )?bank\w*",
        category=A,
        strength=STRONG,
        hint=B,
    ),
    # ----------------------------------------------------------------- Polish: urgency
    _rule(
        "pl.urgency.immediately",
        r"\bnatychmiast\w*|\bbez zwloki\b|\bnie ma czasu\b|\bliczy sie kazda minut\w*",
        category=U,
        strength=STRONG,
    ),
    _rule(
        "pl.urgency.urgent",
        r"\bpiln\w*|\bjak najszybciej\b|\bod razu\b|\bw tej chwili\b",
        category=U,
        strength=WEAK,
    ),
    _rule(
        "pl.urgency.stay_on_line",
        r"\bnie (?:rozlacz|odklada|odloz)\w*",
        category=U,
        strength=WEAK,
    ),
    # ----------------------------------------------------------------- Polish: story context
    _rule("pl.context.grandchild", r"\bwnu(?:cz|k)\w*", context=8, hint=G),
    _rule(
        "pl.context.grandparent_address",
        r"\b(?:babciu|babuniu|dziadku|dziadziu)\b",
        context=6,
        hint=G,
    ),
    _rule(
        "pl.context.accident",
        r"\bwypad(?:ek|ku|kiem)\b|\bpotracil\w*|\bpotracen\w*",
        context=8,
        hint=G,
    ),
    _rule("pl.context.bail", r"\bkaucj\w*|\baresz\w*", context=8, hint=G),
    _rule("pl.context.lawyer", r"\badwokat\w*|\bmecenas\w*|\bprawnik\w*", context=6, hint=G),
    _rule(
        "pl.context.account_at_risk",
        rf"\b(?:kont|srodk|oszczednosc|pieni(?:adz|edz))\w* {_W2}zagrozon\w*"
        rf"|\bzagrozon\w* {_W2}kont\w*|\bwlam\w* na (?:\w+ )?kont\w*|\bnieautoryzowan\w*"
        r"|\bpodejrzan\w* (?:transakc|operac|logowan|przelew)\w*",
        context=10,
        hint=B,
    ),
    _rule(
        "pl.context.remote_access",
        rf"\banydesk\b|\bteamviewer\b|\bquicksupport\b|\bzdaln\w* (?:dostep|pulpit)\w*"
        rf"|\bzainstal\w* {_W2}aplikacj\w*",
        context=10,
        hint=B,
    ),
    _rule("pl.context.loan", r"\bkredyt\w*|\bpozyczk\w*", context=5, hint=B),
    _rule(
        "pl.context.criminals",
        r"\boszust\w*|\bprzestepc\w*|\bzlodziej\w*|\bszajk\w*",
        context=6,
        hint=P,
    ),
    # ----------------------------------------------------------------- English: money
    _rule(
        "en.money.transfer",
        r"\bwire (?:transfer|the money|money|it|funds)\b|\bbank transfer\b|\bmoney transfer\b"
        r"|\btransfer\w* (?:the |your |all |all your )?(?:money|funds|savings)\b",
        category=M,
        strength=STRONG,
    ),
    _rule(
        "en.money.gift_card",
        r"\bgift ?cards?\b|\b(?:itunes|google play|steam|amazon) cards?\b",
        category=M,
        strength=STRONG,
        hint=OTH,
    ),
    _rule("en.money.crypto", r"\bbitcoin\w*|\bcrypto\w*", category=M, strength=STRONG, hint=OTH),
    _rule(
        "en.money.courier",
        rf"\bcourier {_W3}(?:pick|collect|come)\w*"
        r"|\b(?:someone|a man|our agent|an agent|an officer|a driver) will (?:come|pick|collect)\w*"
        r"|\bhand (?:it|the money|the cash|them) (?:over|to)\b",
        category=M,
        strength=STRONG,
        hint=OTH,
    ),
    _rule(
        "en.money.safe_account",
        r"\b(?:safe|secure|protected|holding) account\b",
        category=M,
        strength=STRONG,
        hint=B,
    ),
    _rule(
        "en.money.credentials",
        r"\bpin(?: number| code)?\b|\bcard number\b|\bverification code\b"
        r"|\bone time (?:pass)?code\b|\bsecurity code\b|\b(?:online )?banking password\b",
        category=M,
        strength=STRONG,
        hint=B,
    ),
    # Digits and currency symbols ("$500" is normalised to "usd 500", "2,000 pounds").
    _rule(
        "en.money.amount_digits",
        r"\b(?:usd|gbp|eur) \d+|\b\d+(?: \d{3})*(?: \d+)? ?"
        r"(?:usd|gbp|eur|dollars?|pounds?|euros?|bucks|grand|k)\b",
        category=M,
        strength=WEAK,
    ),
    _rule(
        "en.money.code_digits",
        r"\b(?:code|blik)(?: [a-z]\w*){0,3} \d{3} ?\d{3}(?!\d)",
        category=M,
        strength=STRONG,
        hint=B,
    ),
    _rule("en.money.withdraw", r"\bwithdraw\w*", category=M, strength=WEAK),
    _rule("en.money.cash", r"\bcash\b", category=M, strength=WEAK),
    _rule("en.money.money", r"\bmoney\b|\bsavings\b|\bfunds\b", category=M, strength=WEAK),
    # ----------------------------------------------------------------- English: secrecy
    _rule(
        "en.secrecy.tell_nobody",
        r"\b(?:dont|do not|never) (?:tell|mention|say|speak)\w*"
        r"(?: (?:this|it|about this|about it|a word|anything))? (?:to )?"
        r"(?:anyone|anybody|no one|nobody|my parents|mom and dad|mum and dad"
        r"|your (?:family|son|daughter|children|kids|bank|husband|wife))\b"
        r"|\bkeep (?:this|it) (?:a )?(?:secret|between us|confidential|quiet)\b"
        r"|\btell no one\b|\bno one (?:can|must|should) know\b",
        category=S,
        strength=STRONG,
    ),
    _rule(
        "en.secrecy.operation",
        r"\b(?:secret|undercover|confidential|covert) (?:investigation|operation)\b|\bgag order\b",
        category=S,
        strength=STRONG,
        hint=P,
    ),
    # ----------------------------------------------------------------- English: authority
    _rule(
        "en.authority.claim",
        rf"\b(?:this is|im|i am|calling from|speaking) {_W3}"
        r"(?:police|detective|officer|sergeant|inspector|prosecutor|fbi|irs|hmrc"
        r"|scotland yard|fraud department|fraud team|security department)\b",
        category=A,
        strength=STRONG,
        hint=P,
    ),
    _rule(
        "en.authority.prosecutor",
        r"\bprosecutor\w*|\bdistrict attorney\b|\bfbi\b|\binterpol\b",
        category=A,
        strength=STRONG,
        hint=P,
    ),
    _rule(
        "en.authority.police",
        r"\bpolice\b|\bsheriff\b|\bofficer\b|\bdetective\b",
        category=A,
        strength=WEAK,
        hint=P,
    ),
    _rule(
        "en.authority.bank_employee",
        r"\bbank employee\b|\bbank\w* (?:security|fraud) (?:department|team|officer)\b"
        rf"|\b(?:calling|this is|im|i am) {_W3}(?:from|with) (?:your|the) bank\w*",
        category=A,
        strength=STRONG,
        hint=B,
    ),
    # ----------------------------------------------------------------- English: urgency
    _rule(
        "en.urgency.immediately",
        r"\bimmediately\b|\bright (?:now|away)\b|\bno time\b|\bbefore its too late\b"
        r"|\bwithin the (?:next )?(?:hour|\d+ minutes)\b",
        category=U,
        strength=STRONG,
    ),
    _rule(
        "en.urgency.urgent",
        r"\burgent\w*|\bas soon as possible\b|\basap\b|\bhurry\b|\bquickly\b",
        category=U,
        strength=WEAK,
    ),
    _rule(
        "en.urgency.stay_on_line",
        r"\b(?:dont|do not) hang up\b|\bstay on the line\b",
        category=U,
        strength=WEAK,
    ),
    # ----------------------------------------------------------------- English: story context
    _rule(
        "en.context.grandchild",
        r"\bgrand(?:son|daughter|child|children|kid)s?\b",
        context=8,
        hint=G,
    ),
    _rule(
        "en.context.grandparent_address",
        r"\b(?:grandma|grandpa|granny|grandad|nana)\b",
        context=6,
        hint=G,
    ),
    _rule(
        "en.context.accident",
        r"\baccident\b|\bcar crash\b|\bhit (?:a|someone|somebody)\b",
        context=8,
        hint=G,
    ),
    _rule("en.context.bail", r"\bbail\b|\bjail\b|\barrested\b|\bin custody\b", context=8, hint=G),
    _rule("en.context.lawyer", r"\blawyer\b|\battorney\b|\bsolicitor\b", context=6, hint=G),
    _rule(
        "en.context.account_at_risk",
        r"\baccount (?:is |has been |was )?"
        r"(?:at risk|compromised|hacked|frozen|blocked|suspended)\b"
        r"|\b(?:savings|money|funds) (?:are |is )?(?:at risk|in danger|not safe)\b"
        r"|\bsuspicious (?:activity|transaction|login)s?\b"
        r"|\bunauthori[sz]ed (?:transaction|payment|access)s?\b"
        r"|\bfraudulent (?:transaction|activity)\b",
        context=10,
        hint=B,
    ),
    _rule(
        "en.context.remote_access",
        r"\banydesk\b|\bteamviewer\b|\bremote (?:access|desktop|support)\b"
        r"|\binstall\w* (?:an |the |this )?app\w*",
        context=10,
        hint=B,
    ),
    _rule(
        "en.context.criminals",
        r"\bcriminals?\b|\bfraudsters?\b|\bscammers?\b|\bmoney laundering\b",
        context=6,
        hint=P,
    ),
)

# ---------------------------------------------------------------------------- scoring
CATEGORY_POINTS: dict[Category, int] = {M: 24, S: 26, A: 18, U: 12}
PAIR_BONUS: dict[frozenset[Category], int] = {
    frozenset({M, S}): 22,
    frozenset({M, A}): 20,
    frozenset({M, U}): 10,
    frozenset({A, S}): 12,
    frozenset({A, U}): 6,
    frozenset({S, U}): 6,
}
CONTEXT_CAP = 20
MONEY_WITH_STORY_BONUS = 20  # money + a full scam story (>= 8 context points)
MONEY_WITH_HINT_BONUS = 10  # money + a weaker story element
THREE_SIGNS_BONUS = 10  # three or more categories, at least one strong
SCAM_TYPE_MIN_SCORE = 30


@dataclass(frozen=True)
class RulesResult:
    score: int
    categories: dict[Category, float] = field(default_factory=dict)
    context_points: int = 0
    scam_type: ScamType = ScamType.NONE
    matched: tuple[str, ...] = ()

    def flags(self) -> dict[str, bool]:
        return {c.value: self.categories.get(c, 0.0) > 0 for c in Category}


_TRANSLATE = str.maketrans(
    {"ł": "l", "Ł": "L", "’": "", "'": "", "`": "", "$": " usd ", "£": " gbp ", "€": " eur "}
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Lowercase, strip diacritics and punctuation, collapse whitespace."""
    text = text.translate(_TRANSLATE)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _NON_ALNUM.sub(" ", text.lower())
    return f" {text.strip()} "


def _rules_for(lang: Lang | None) -> Iterable[Rule]:
    if lang is None:
        return RULES
    return (rule for rule in RULES if rule.lang == lang)


def score_text(text: str, lang: Lang | None = None) -> RulesResult:
    """Score `text` against the rules. `lang=None` applies both languages."""
    normalized = normalize(text)
    if not normalized.strip():
        return RulesResult(score=0)

    categories: dict[Category, float] = {}
    context = 0
    hints: dict[ScamType, float] = {}
    matched: list[str] = []
    for rule in _rules_for(lang):
        if not rule.pattern.search(normalized):
            continue
        matched.append(rule.id)
        if rule.category is not None:
            categories[rule.category] = max(categories.get(rule.category, 0.0), rule.strength)
        context += rule.context_points
        if rule.hint is not None:
            weight = rule.strength * 10 if rule.category is not None else rule.context_points
            hints[rule.hint] = hints.get(rule.hint, 0.0) + weight

    context = min(context, CONTEXT_CAP)
    score = _combine(categories, context)
    return RulesResult(
        score=score,
        categories=categories,
        context_points=context,
        scam_type=_scam_type(score, categories, hints),
        matched=tuple(matched),
    )


def _combine(categories: dict[Category, float], context: int) -> int:
    total = float(context)
    for category, strength in categories.items():
        total += CATEGORY_POINTS[category] * strength
    for pair in combinations(categories, 2):
        total += PAIR_BONUS[frozenset(pair)] * min(categories[pair[0]], categories[pair[1]])
    money = categories.get(M, 0.0)
    if money and context >= 8:
        total += MONEY_WITH_STORY_BONUS * money
    elif money and context > 0:
        total += MONEY_WITH_HINT_BONUS * money
    if len(categories) >= 3 and max(categories.values()) >= STRONG:
        total += THREE_SIGNS_BONUS
    return max(0, min(100, round(total)))


def _scam_type(
    score: int, categories: dict[Category, float], hints: dict[ScamType, float]
) -> ScamType:
    if score < SCAM_TYPE_MIN_SCORE:
        return ScamType.NONE
    if hints:
        # Ties resolve in this order (police calls often wrap a "grandchild" story).
        order = [ScamType.POLICE, ScamType.BANK, ScamType.GRANDCHILD, ScamType.OTHER]
        return max(order, key=lambda t: (hints.get(t, 0.0), -order.index(t)))
    return ScamType.OTHER if categories else ScamType.NONE
