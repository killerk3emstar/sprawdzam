import pytest

from app.risk.models import Category, ScamType
from app.risk.rules import RULES, normalize, score_text

WARN = 50
HANGUP = 80

FULL_SCAMS = [
    # (lang, text, expected scam type)
    (
        "pl",
        "Dzień dobry, mówi komisarz Nowak z CBŚ. Prowadzimy tajną akcję przeciwko oszustom. "
        "Pani oszczędności są zagrożone. Proszę wypłacić gotówkę i przekazać ją kurierowi. "
        "Proszę nikomu o tym nie mówić.",
        ScamType.POLICE,
    ),
    (
        "pl",
        "Dzień dobry, dzwonię z działu bezpieczeństwa banku. Odnotowaliśmy podejrzaną transakcję, "
        "pani konto jest zagrożone. Musimy natychmiast przelać środki na bezpieczne konto.",
        ScamType.BANK,
    ),
    (
        "pl",
        "Babciu, to ja, twój wnuczek. Miałem wypadek i potrzebuję pilnie pieniędzy na kaucję. "
        "Tylko nie mów nic rodzicom.",
        ScamType.GRANDCHILD,
    ),
    ("pl", "Proszę podać kod BLIK, tylko nikomu nie mów, to pilne.", ScamType.BANK),
    (
        "en",
        "This is detective Brown from the police department. Your savings are at risk. You must "
        "withdraw cash right now, a courier will pick it up. Don't tell anyone, this is a secret "
        "investigation.",
        ScamType.POLICE,
    ),
    (
        "en",
        "Hello, I'm calling from your bank's fraud department. We detected suspicious activity and "
        "your account has been compromised. You need to transfer your funds to a safe account "
        "immediately.",
        ScamType.BANK,
    ),
    (
        "en",
        "Grandma, it's me, your grandson. I had a car accident and I need money for bail right "
        "away. Please don't tell mom and dad.",
        ScamType.GRANDCHILD,
    ),
    ("en", "Buy gift cards and read me the codes, it's urgent, don't tell anyone.", ScamType.OTHER),
]

PARTIAL_SCAMS = [
    # Scam openers without the secrecy part: should warn, not hang up.
    ("pl", "Babciu, to ja, twój wnuczek. Miałem wypadek i potrzebuję pilnie pieniędzy na kaucję."),
    (
        "en",
        "Grandma, it's me, your grandson. I had a car accident and I need money for bail "
        "right away.",
    ),
    ("pl", "Przelej pieniądze i nikomu nie mów."),
]

NORMAL_TALK = [
    # Everyday family conversations, including about money: must stay below RISK_WARN.
    (
        "pl",
        "Cześć mamo, wpadnę w niedzielę na obiad. Przelałem ci już pieniądze za rachunek "
        "za prąd, sprawdź w banku.",
    ),
    (
        "pl",
        "Babciu, wszystkiego najlepszego! Kupiłem ci prezent, a pieniądze od ciebie odłożę "
        "na wakacje.",
    ),
    (
        "pl",
        "Wnuczek miał mały wypadek na rowerze, ale wszystko dobrze. Policja tylko spisała "
        "świadków.",
    ),
    ("pl", "Synku, potrzebuję pilnie pieniędzy na leki, możesz mi przelać dwieście złotych?"),
    ("pl", "Zbieramy pieniądze na prezent dla mamy, tylko nie mów jej, to niespodzianka."),
    ("pl", "Kurier przyniósł dziś paczkę, zapłaciłam gotówką."),
    ("pl", "Widziałaś w telewizji? Prokurator oskarżył tego polityka."),
    ("pl", "Jutro idę do banku wpłacić pieniądze na lokatę."),
    ("en", "Hi grandma, thanks for the birthday money! I used the cash to buy a new book."),
    ("en", "Dad, can you transfer me some money for rent? I'll pay you back next week."),
    ("en", "The police closed the road after an accident near the bank, so I was late."),
    ("en", "We're planning a surprise party for mom, keep it a secret!"),
    ("en", "I bought a gift card for your birthday, I hope you like it."),
    ("en", "My daughter is a bank employee, she works in the city centre."),
]


@pytest.mark.parametrize(("lang", "text", "scam_type"), FULL_SCAMS)
def test_full_scams_reach_hangup_threshold(lang, text, scam_type):
    result = score_text(text, lang)
    assert result.score >= HANGUP, result
    assert result.scam_type is scam_type


@pytest.mark.parametrize(("lang", "text"), PARTIAL_SCAMS)
def test_partial_scams_warn(lang, text):
    result = score_text(text, lang)
    assert WARN <= result.score < HANGUP, result


@pytest.mark.parametrize(("lang", "text"), NORMAL_TALK)
def test_normal_family_talk_stays_below_warn(lang, text):
    result = score_text(text, lang)
    assert result.score < WARN, result


def test_single_words_score_low():
    for text in ["pieniądze", "gotówka", "policja", "pilne", "money", "cash", "police", "urgent"]:
        assert score_text(text).score < 25, text


def test_combination_scores_much_higher_than_single_signs():
    money = score_text("przelej pieniądze", "pl").score
    secrecy = score_text("nikomu nie mów", "pl").score
    authority = score_text("jestem policjantem", "pl").score
    combined = score_text("jestem policjantem, przelej pieniądze, nikomu nie mów", "pl").score
    assert combined >= HANGUP
    assert combined > money + secrecy + authority - 10


def test_matching_ignores_case_and_diacritics():
    variants = ["PRZELAĆ", "przelac", "Przelać!", "przelew", "przelej", "przelał"]
    for text in variants:
        result = score_text(text, "pl")
        assert result.categories.get(Category.MONEY) == 1.0, text
    assert normalize("Łódź, ŻÓŁĆ! Don't") == " lodz zolc dont "
    assert score_text("NIKOMU NIE MÓW", "pl").categories[Category.SECRECY] == 1.0
    assert score_text("nikomu nie mow", "pl").categories[Category.SECRECY] == 1.0


def test_repetition_does_not_inflate_score():
    once = score_text("pieniądze", "pl").score
    many = score_text("pieniądze pieniądze pieniądze pieniędzy pieniądze", "pl").score
    assert once == many


def test_language_filter():
    english = "don't tell anyone, wire transfer"
    assert score_text(english, "pl").score == 0
    assert score_text(english, "en").score >= WARN
    assert score_text(english).score == score_text(english, "en").score


def test_empty_text():
    result = score_text("   ", "pl")
    assert result.score == 0
    assert result.scam_type is ScamType.NONE


def test_flags_and_ids():
    result = score_text("kod BLIK", "pl")
    assert result.flags() == {"money": True, "secrecy": False, "authority": False, "urgency": False}
    assert "pl.money.blik" in result.matched


def test_rule_ids_are_unique_and_prefixed():
    ids = [rule.id for rule in RULES]
    assert len(ids) == len(set(ids))
    assert all(rule.id.startswith(("pl.", "en.")) for rule in RULES)
