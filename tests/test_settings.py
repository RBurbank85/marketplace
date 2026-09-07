from pathlib import Path

import pytest
from pydantic import ValidationError

from config.settings import BASE_DIR, CollectorConfig, Settings


def test_settings_loads_values_from_env_file(tmp_path: Path) -> None:
    database_path = tmp_path / "maie.db"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                f"SQLITE_PATH={database_path}",
                "SEARCH_INTERVAL=7",
                "SEARCH_RADIUS=12",
                "DISCORD_WEBHOOK=https://discord.com/api/webhooks/123/abc",
                "TELEGRAM_TOKEN=123456789:ABCDEF1234567890",
                "MINIMUM_FLIPSCORE=80",
                "MINIMUM_EXPECTED_PROFIT=45.5",
                "LOGGING_LEVEL=DEBUG",
                "ENABLED_COLLECTORS=craigslist,ebay",
                "ENABLED_CATEGORIES=electronics,tools",
            ]
        )
    )

    settings = Settings(_env_file=env_file)

    assert settings.sqlite_path == database_path
    assert settings.search_interval == 7
    assert settings.search_radius == 12
    assert settings.discord_webhook == "https://discord.com/api/webhooks/123/abc"
    assert settings.telegram_token == "123456789:ABCDEF1234567890"
    assert settings.minimum_flipscore == 80
    assert settings.minimum_expected_profit == 45.5
    assert settings.logging_level == "DEBUG"
    assert settings.enabled_collectors == ["craigslist", "ebay"]
    assert settings.enabled_categories == ["electronics", "tools"]


def test_settings_resolves_relative_sqlite_path_from_project_root() -> None:
    settings = Settings(sqlite_path=Path("database") / "custom.db")

    assert settings.sqlite_path == (BASE_DIR / "database" / "custom.db").resolve()


def test_environment_sqlite_path_overrides_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SQLITE_PATH=database/from-file.db\n")
    environment_path = tmp_path / "from-environment.db"
    monkeypatch.setenv("sqlite_path", str(environment_path))

    settings = Settings(_env_file=env_file)

    assert settings.sqlite_path == environment_path


def test_settings_rejects_invalid_values() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(discord_webhook="https://example.com/not-a-webhook")

    message = str(exc_info.value)
    assert "Discord webhook" in message
    assert "valid Discord webhook URL" in message

    with pytest.raises(ValidationError) as exc_info:
        Settings(logging_level="VERBOSE")

    message = str(exc_info.value)
    assert "logging_level" in message
    assert "DEBUG, INFO, WARNING, ERROR, CRITICAL" in message


def test_collector_configuration_is_typed_and_redacted() -> None:
    settings = Settings(
        enabled_collectors="craigslist, test",
        collector_configs={
            "test": {
                "queries": "guitar, amplifier",
                "locations": ["Seattle"],
                "pagination_limit": 3,
                "request_timeout": 4.5,
                "rate_limit_per_minute": 12,
                "credentials": {"token": "secret-token"},
            }
        },
    )

    config = settings.collector_configs["test"]
    assert isinstance(config, CollectorConfig)
    assert config.queries == ["guitar", "amplifier"]
    assert config.credentials["token"].get_secret_value() == "secret-token"
    assert "credentials" not in config.public_dump()
    assert "secret-token" not in str(settings.public_dump())


def test_collector_configuration_rejects_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        CollectorConfig(pagination_limit=0)
