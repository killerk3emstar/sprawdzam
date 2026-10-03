"""Application settings loaded from environment variables (and an optional `.env` file).

Variable names match `.env.example` at the repository root. Secret values are kept in
`SecretStr` so they never end up in logs, reprs or the `/health` response.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.telephony.numbers import is_e164, parse_number_list

Lang = Literal["pl", "en"]
DecisionBackendName = Literal["basal", "clef", "rules"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Root `.env` (shared with docker compose) first, then an optional `server/.env` override.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        # Never echo env values (tokens, phone numbers) in validation error messages.
        hide_input_in_errors=True,
    )

    # Public base URL of the backend (tunnel or AWS). Used to build the <Stream> URL and to
    # reconstruct the exact URL Twilio signed, because the app runs behind a proxy.
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: SecretStr = SecretStr("")
    TWILIO_API_KEY_SID: str = ""
    TWILIO_API_KEY_SECRET: SecretStr = SecretStr("")
    TWILIO_TWIML_APP_SID: str = ""
    TWILIO_NUMBER: str = ""
    # Development only: accept webhooks without a valid X-Twilio-Signature when no auth token
    # is configured. Never enable in production.
    ALLOW_UNSIGNED_WEBHOOKS: bool = False

    # Self-hosted model endpoints
    WHISPER_URL: str = ""
    DECISION_BACKEND: DecisionBackendName = "rules"
    BASAL_URL: str = ""
    CLEF_URL: str = ""
    DECISION_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0, le=30)
    HF_TOKEN: SecretStr = SecretStr("")

    # Audio pipeline
    STT_WINDOW_SECONDS: float = Field(default=3.0, ge=1.0, le=10.0)
    STT_TIMEOUT_SECONDS: float = Field(default=8.0, gt=0, le=60)

    # Risk thresholds (0-100)
    RISK_WARN: int = Field(default=50, ge=0, le=100)
    RISK_HANGUP: int = Field(default=80, ge=0, le=100)

    # Language used for voice prompts and speech recognition until per-senior settings exist
    DEFAULT_LANG: Lang = "pl"

    # Telephony cost and safety limits (see app/telephony/guard.py and admission.py)
    # Outbound calls, SMS and REST hang-ups are only logged unless this is explicitly false.
    TELEPHONY_DRY_RUN: bool = True
    # Comma-separated E.164 numbers that outbound calls/SMS may go to. Empty = none.
    OUTBOUND_ALLOWLIST: str = ""
    # Trusted person alerted on high risk (E.164; must also be on OUTBOUND_ALLOWLIST).
    TRUSTED_PERSON_NUMBER: str = ""
    MAX_OUTBOUND_CALLS_PER_DAY: int = Field(default=10, ge=0, le=1000)
    MAX_SMS_PER_DAY: int = Field(default=20, ge=0, le=1000)
    MAX_CONCURRENT_CALLS: int = Field(default=2, ge=1, le=100)
    MAX_CALL_SECONDS: float = Field(default=600, gt=0, le=4 * 3600)
    MAX_INCOMING_CALLS_PER_MINUTE: int = Field(default=10, ge=1, le=1000)
    # Directory for the persisted daily counters (no phone numbers or content are stored).
    DATA_DIR: str = "data"

    # Senior app relay (protocol v0, docs/APP_PROTOCOL.md)
    # Shared secret of the senior's device for WS /app/control (>= 16 characters).
    APP_DEVICE_TOKEN: SecretStr = SecretStr("")
    # Ringing time before an unanswered protected call is ended.
    APP_ACCEPT_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=300)
    # Family password (digits, entered as DTMF by the caller or the senior). Empty = none:
    # a high-risk call is then blocked right after the verify_password prompt.
    FAMILY_PASSWORD: SecretStr = SecretStr("")
    VERIFY_PASSWORD_SECONDS: float = Field(default=20.0, gt=0, le=120)

    # Browser test pages /dev/caller and /dev/senior (never enable in production).
    DEV_TOOLS: bool = False

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("PUBLIC_BASE_URL")
    @classmethod
    def _check_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("https://", "http://")):
            raise ValueError("PUBLIC_BASE_URL must start with https:// or http://")
        if "?" in value or "#" in value:
            raise ValueError("PUBLIC_BASE_URL must not contain a query string or fragment")
        return value

    @field_validator("DEFAULT_LANG", mode="before")
    @classmethod
    def _lower_lang(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("DECISION_BACKEND", mode="before")
    @classmethod
    def _lower_backend(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("TWILIO_NUMBER", "TRUSTED_PERSON_NUMBER")
    @classmethod
    def _check_e164(cls, value: str) -> str:
        value = value.strip().replace(" ", "")
        if value and not is_e164(value):
            raise ValueError("must be an E.164 phone number, e.g. +48123456789")
        return value

    @field_validator("APP_DEVICE_TOKEN")
    @classmethod
    def _check_device_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if token and (len(token) < 16 or token != token.strip()):
            raise ValueError("APP_DEVICE_TOKEN must be at least 16 characters, no spaces")
        return value

    @field_validator("FAMILY_PASSWORD")
    @classmethod
    def _check_family_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if password and not re.fullmatch(r"[0-9]{3,12}", password):
            raise ValueError("FAMILY_PASSWORD must be 3-12 digits")
        return value

    @field_validator("OUTBOUND_ALLOWLIST")
    @classmethod
    def _check_allowlist(cls, value: str) -> str:
        parse_number_list(value)  # raises ValueError on a malformed entry
        return value

    @model_validator(mode="after")
    def _check_thresholds(self) -> Settings:
        if self.RISK_WARN >= self.RISK_HANGUP:
            raise ValueError("RISK_WARN must be lower than RISK_HANGUP")
        return self

    @property
    def outbound_allowlist(self) -> frozenset[str]:
        return parse_number_list(self.OUTBOUND_ALLOWLIST)

    @property
    def twilio_auth_token(self) -> str:
        return self.TWILIO_AUTH_TOKEN.get_secret_value()

    def ws_url(self, path: str) -> str:
        """Public WebSocket URL for `path` (https -> wss, http -> ws)."""
        base = self.PUBLIC_BASE_URL
        if base.startswith("https://"):
            base = "wss://" + base.removeprefix("https://")
        else:
            base = "ws://" + base.removeprefix("http://")
        return f"{base}{path}"

    def public_url(self, path: str, query: str = "") -> str:
        url = f"{self.PUBLIC_BASE_URL}{path}"
        return f"{url}?{query}" if query else url


@lru_cache
def get_settings() -> Settings:
    return Settings()
