from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


def _parse_csv_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item.strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        if not value.strip():
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    raise TypeError("Expected a comma-separated string or a list of values")


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env files."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(
        default="maie", description="Application name shown in CLI output and logs."
    )
    environment: str = Field(
        default="development", description="Deployment environment name."
    )
    debug: bool = Field(default=False, description="Enable verbose debug diagnostics.")
    sqlite_path: Path = Field(
        default=BASE_DIR / "database" / "listings.db",
        description="Path to the SQLite database file used by the application.",
    )
    database_url: Optional[str] = Field(
        default=None,
        description="Full database connection URL (e.g., postgresql://user:pass@host/db). If provided, takes precedence over sqlite_path.",
    )
    search_interval: int = Field(
        default=15, ge=1, description="How often searches should run, in minutes."
    )
    max_concurrent_collectors: int = Field(
        default=5,
        ge=1,
        description="Maximum number of collectors allowed to run concurrently.",
    )
    search_radius: int = Field(
        default=25, ge=1, description="Maximum search radius in miles."
    )
    discord_webhook: Optional[str] = Field(
        default=None, description="Discord webhook URL for sending alerts."
    )
    telegram_token: Optional[str] = Field(
        default=None, description="Telegram bot token for sending alerts."
    )
    minimum_flipscore: int = Field(
        default=60,
        ge=0,
        le=100,
        description="Minimum FlipScore required for an opportunity to be surfaced.",
    )
    minimum_expected_profit: float = Field(
        default=20.0,
        ge=0.0,
        description="Minimum expected profit in dollars required for a listing to be considered.",
    )
    logging_level: str = Field(
        default="INFO",
        description="Logging verbosity. Supported values: DEBUG, INFO, WARNING, ERROR, CRITICAL.",
    )
    enabled_collectors: Any = Field(
        default_factory=lambda: ["craigslist"],
        description="Comma-separated collector names that should be enabled.",
    )
    enabled_categories: Any = Field(
        default_factory=lambda: ["electronics", "tools"],
        description="Comma-separated category slugs that should be enabled.",
    )
    # Security
    api_key: Optional[str] = Field(
        default=None, description="API key for securing the FastAPI application."
    )
    secret_key: str = Field(
        default="secret-key-change-me-in-production",
        description="Secret key for JWT and other cryptographic operations.",
    )
    cors_origins: Any = Field(
        default_factory=lambda: [
            "http://localhost",
            "http://localhost:3000",
            "http://localhost:8000",
        ],
        description="Comma-separated list of origins allowed to make cross-site requests.",
    )
    rate_limit_requests_per_minute: Optional[int] = Field(
        default=60,
        ge=0,
        description="Requests per minute per client; set to 0 to disable rate limiting.",
    )

    # Networking
    network_timeout: int = Field(
        default=10, ge=1, description="Default timeout in seconds for network requests."
    )
    network_max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum number of retries for failed network requests.",
    )
    network_retry_backoff: float = Field(
        default=2.0,
        ge=0.0,
        description="Exponential backoff factor for network retries.",
    )
    network_user_agent: str = Field(
        default="MAIE/0.1.0",
        description="Default User-Agent header for network requests.",
    )
    network_proxy: Optional[str] = Field(
        default=None, description="HTTP proxy URL to use for all network requests."
    )

    # AI Settings
    ai_enabled: bool = Field(
        default=False, description="Enable AI-powered analysis features."
    )
    ai_provider: str = Field(
        default="local",
        description="Primary AI provider: local, openrouter, huggingface.",
    )
    ai_model: str = Field(
        default="llama3", description="Specific model name to use for AI tasks."
    )
    ai_api_key: Optional[str] = Field(
        default=None, description="API key for the selected AI provider."
    )
    ai_base_url: Optional[str] = Field(
        default=None, description="Base URL for local or custom AI endpoints."
    )
    ai_timeout: int = Field(
        default=30, ge=1, description="Timeout in seconds for AI provider requests."
    )
    ai_max_retries: int = Field(
        default=3, ge=0, description="Maximum number of retries for failed AI requests."
    )

    flipscore_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "price": 2.0,
            "demand": 1.5,
            "seller": 1.0,
            "risk": 1.5,
            "distance": 0.8,
            "repair": 1.0,
            "seasonality": 0.5,
            "confidence": 0.5,
            "competition": 0.7,
            "historical": 0.5,
        },
        description="Weights for the modular FlipScore pipeline components.",
    )

    @field_validator("sqlite_path", mode="before")
    @classmethod
    def _normalize_sqlite_path(cls, value: Any) -> Path:
        if value in (None, ""):
            return BASE_DIR / "database" / "listings.db"
        if isinstance(value, Path):
            path = value
        elif isinstance(value, str):
            path = Path(value.strip())
        else:
            raise TypeError("sqlite_path must be a path-like value")

        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
        return path

    @field_validator(
        "enabled_collectors", "enabled_categories", "cors_origins", mode="before"
    )
    @classmethod
    def _parse_enabled_options(cls, value: Any) -> List[str]:
        return _parse_csv_list(value)

    @field_validator("discord_webhook", mode="before")
    @classmethod
    def _validate_discord_webhook(cls, value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise TypeError("Discord webhook must be provided as a string")

        normalized = value.strip()
        if "discord.com" not in normalized and "discordapp.com" not in normalized:
            raise ValueError(
                "Discord webhook must be a valid Discord webhook URL, for example https://discord.com/api/webhooks/..."
            )
        if "/api/webhooks/" not in normalized:
            raise ValueError(
                "Discord webhook must point to a Discord webhook endpoint, for example https://discord.com/api/webhooks/..."
            )
        return normalized

    @field_validator("telegram_token", mode="before")
    @classmethod
    def _validate_telegram_token(cls, value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise TypeError("Telegram token must be provided as a string")

        normalized = value.strip()
        if ":" not in normalized:
            raise ValueError("Telegram token must look like 123456789:ABCDEF1234567890")
        return normalized

    @field_validator("logging_level")
    @classmethod
    def _validate_logging_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(
                "logging_level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        return normalized


settings = Settings()
