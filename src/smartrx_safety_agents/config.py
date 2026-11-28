"""Centralized application configuration with fail-closed production secret checks."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET_VALUES: frozenset[str] = frozenset(
    {"", "changeme", "default", "secret", "test", "placeholder", "none"}
)


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    gemini_model_name: str = Field(default="gemini-3.8-flash-high")
    gemini_api_key: SecretStr | None = Field(default=None)
    gemini_thinking_budget: int = Field(default=2048, ge=0)
    max_output_tokens: int = Field(default=8192, ge=1, le=8192)
    openrouter_api_key: SecretStr | None = Field(default=None)

    environment: Literal["development", "staging", "production"] = Field(default="development")
    require_auth: bool = Field(default=False)
    mcp_api_key: SecretStr | None = Field(default=None)
    plan_signing_secret: SecretStr | None = Field(default=None)
    smartrx_safety_agents_webhook_secret: SecretStr | None = Field(default=None)

    smartrx_port: int = Field(default=8080, ge=1, le=65535)
    max_payload_size_bytes: int = Field(default=10_485_760, ge=1024, le=10_485_760)

    smartrx_db_path: Path = Field(default=Path("data/smartrx_ledger.db"))
    audit_log_dir: Path = Field(default=Path("audit_logs"))
    filelock_timeout_sec: float = Field(default=10.0, gt=0.0)

    max_session_token_budget: int = Field(default=500_000, gt=0)
    daily_api_cost_limit_usd: float = Field(default=10.0, gt=0.0)

    @staticmethod
    def _is_valid_secret(secret: SecretStr | None) -> bool:
        if secret is None:
            return False
        raw = secret.get_secret_value().strip()
        return len(raw) >= 16 and raw.casefold() not in _INSECURE_SECRET_VALUES

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Settings:
        """Fail closed at startup if production secrets or required auth keys are missing."""
        if self.environment == "production":
            if not self._is_valid_secret(self.plan_signing_secret):
                raise RuntimeError(
                    "PLAN_SIGNING_SECRET must be set to a strong (>=16 char) secret in production."
                )
            if not self._is_valid_secret(self.smartrx_safety_agents_webhook_secret):
                raise RuntimeError(
                    "SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET must be set to a strong "
                    "(>=16 char) secret in production."
                )
        if (self.environment == "production" or self.require_auth) and not self._is_valid_secret(
            self.mcp_api_key
        ):
            raise RuntimeError(
                "MCP_API_KEY must be set to a strong (>=16 char) key when auth is required."
            )
        return self


def get_settings() -> Settings:
    """Instantiate and validate runtime settings."""
    return Settings()
