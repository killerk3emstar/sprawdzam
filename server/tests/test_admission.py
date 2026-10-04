import pytest

from app.telephony.admission import CallAdmission, SlidingWindowRateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_concurrency_limit_counts_pending_and_active():
    admission = CallAdmission(max_concurrent=2)
    token_a = admission.admit("CA_a")
    token_b = admission.admit("CA_b")
    assert token_a and token_b
    assert admission.admit("CA_c") is None  # full (two pending)
    assert admission.activate("CA_a", token_a)
    assert admission.admit("CA_c") is None  # still full (one active, one pending)
    admission.release("CA_a")
    assert admission.admit("CA_c") is not None


def test_token_is_single_use_and_bound_to_call():
    admission = CallAdmission(max_concurrent=2)
    token = admission.admit("CA_a")
    assert not admission.activate("CA_b", token)
    assert not admission.activate("CA_a", "forged")
    assert admission.activate("CA_a", token)
    assert not admission.activate("CA_a", token)  # already consumed


def test_twilio_retry_reuses_slot():
    admission = CallAdmission(max_concurrent=1)
    first = admission.admit("CA_a")
    second = admission.admit("CA_a")
    assert first and second and first != second
    assert admission.pending_count == 1
    assert not admission.activate("CA_a", first)  # replaced by the retry's token
    assert admission.admit("CA_a") is not None


def test_expired_tokens_free_the_slot():
    clock = Clock()
    admission = CallAdmission(max_concurrent=1, token_ttl=60, clock=clock)
    token = admission.admit("CA_a")
    assert admission.admit("CA_b") is None
    clock.now += 61
    assert admission.admit("CA_b") is not None
    assert not admission.activate("CA_a", token)


def test_activate_returns_caller_and_lang():
    admission = CallAdmission(max_concurrent=1)
    token = admission.admit("CA_a", caller="+48500000001", lang="en")
    admitted = admission.activate("CA_a", token)
    assert admitted.caller == "+48500000001" and admitted.lang == "en"
    assert admission.activate("CA_b", "") is None


def test_active_call_cannot_be_admitted_twice():
    admission = CallAdmission(max_concurrent=3)
    token = admission.admit("CA_a")
    assert admission.activate("CA_a", token)
    assert admission.admit("CA_a") is None


def test_rate_limiter_sliding_window():
    clock = Clock()
    limiter = SlidingWindowRateLimiter(limit=3, window=60, clock=clock)
    assert [limiter.allow() for _ in range(4)] == [True, True, True, False]
    clock.now += 30
    assert not limiter.allow()
    clock.now += 31
    assert limiter.allow()


def test_invalid_limits():
    with pytest.raises(ValueError):
        CallAdmission(max_concurrent=0)
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(limit=0)
