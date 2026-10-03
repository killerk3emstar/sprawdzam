import pytest
from pydantic import ValidationError

from app.config import Settings


def make(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_defaults_are_safe():
    settings = make()
    assert settings.TELEPHONY_DRY_RUN is True
    assert settings.DEV_TOOLS is False
    assert settings.ALLOW_UNSIGNED_WEBHOOKS is False
    assert settings.outbound_allowlist == frozenset()


def test_ws_url():
    assert make(PUBLIC_BASE_URL="https://a.example/").ws_url("/twilio/stream") == (
        "wss://a.example/twilio/stream"
    )
    assert make(PUBLIC_BASE_URL="http://localhost:8000").ws_url("/x") == "ws://localhost:8000/x"


@pytest.mark.parametrize(
    "values",
    [
        {"APP_DEVICE_TOKEN": "short"},
        {"APP_DEVICE_TOKEN": " padded-token-0123456789 "},
        {"FAMILY_PASSWORD": "12ab"},
        {"FAMILY_PASSWORD": "12"},
        {"RISK_WARN": 80, "RISK_HANGUP": 50},
        {"OUTBOUND_ALLOWLIST": "+48600000001, 600000002"},
        {"TWILIO_NUMBER": "600000001"},
        {"PUBLIC_BASE_URL": "ftp://x"},
        {"DEFAULT_LANG": "de"},
    ],
)
def test_invalid_values_rejected(values):
    with pytest.raises(ValidationError) as info:
        make(**values)
    # Validation errors never echo the (possibly secret) input.
    for value in values.values():
        if isinstance(value, str) and len(value) > 3:
            assert value not in str(info.value)


def test_valid_relay_settings():
    settings = make(APP_DEVICE_TOKEN="x" * 32, FAMILY_PASSWORD="2468", DEFAULT_LANG="EN")
    assert settings.FAMILY_PASSWORD.get_secret_value() == "2468"
    assert settings.DEFAULT_LANG == "en"
    assert "x" * 32 not in repr(settings)
