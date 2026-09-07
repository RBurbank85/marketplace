from __future__ import annotations

import httpx
import pytest

from alerts.discord import DiscordNotification, DiscordNotificationError
from alerts.notifications import AlertNotification, Notification, NotificationService


class RecordingNotification(Notification):
    def __init__(self) -> None:
        self.sent: list[AlertNotification] = []

    def send(self, alert: AlertNotification) -> None:
        self.sent.append(alert)


def test_discord_notification_builds_expected_payload() -> None:
    sent_payloads: list[tuple[str, dict[str, object]]] = []

    def fake_post(url: str, payload: dict[str, object]) -> None:
        sent_payloads.append((url, payload))

    provider = DiscordNotification(
        webhook_url="https://discord.com/api/webhooks/123/abc",
        http_client=fake_post,
    )
    alert = AlertNotification(
        title="Vintage gaming console",
        price=149.0,
        estimated_value=260.0,
        expected_profit=111.0,
        flip_score=88,
        confidence=0.93,
        reasoning="Great demand and low competition",
        listing_url="https://example.com/listing/123",
    )

    provider.send(alert)

    assert len(sent_payloads) == 1
    url, payload = sent_payloads[0]
    assert url == "https://discord.com/api/webhooks/123/abc"
    assert payload["content"] == "New flip opportunity: Vintage gaming console"
    assert payload["embeds"][0]["title"] == "Vintage gaming console"
    assert payload["embeds"][0]["description"] == "Great demand and low competition"
    assert payload["embeds"][0]["fields"][0]["name"] == "Price"
    assert payload["embeds"][0]["fields"][0]["value"] == "$149.00"


def test_notification_service_dispatches_to_all_providers() -> None:
    first = RecordingNotification()
    second = RecordingNotification()
    service = NotificationService([first, second])
    alert = AlertNotification(
        title="Desk lamp",
        price=35.0,
        estimated_value=65.0,
        expected_profit=30.0,
        flip_score=72,
        confidence=0.79,
        reasoning="Solid margin",
        listing_url="https://example.com/listing/456",
    )

    service.send(alert)

    assert [provider.sent[0].title for provider in (first, second)] == [
        "Desk lamp",
        "Desk lamp",
    ]
    assert first.sent[0].listing_url == "https://example.com/listing/456"
    assert second.sent[0].expected_profit == 30.0


def test_discord_notification_can_be_disabled_without_configuration() -> None:
    provider = DiscordNotification()

    provider.send(
        AlertNotification(
            title="Unused alert",
            price=1.0,
            estimated_value=2.0,
            expected_profit=1.0,
            flip_score=60,
            confidence=0.5,
            reasoning="Not sent",
            listing_url="https://example.com/listing/789",
        )
    )


def test_discord_notification_rejects_invalid_webhook() -> None:
    with pytest.raises(ValueError, match="valid Discord webhook URL"):
        DiscordNotification(webhook_url="https://example.com/webhook")


def test_discord_notification_wraps_http_failures_without_secret() -> None:
    webhook_url = "https://discord.com/api/webhooks/123/secret-token"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    provider = DiscordNotification(
        webhook_url=webhook_url,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(DiscordNotificationError) as exc_info:
        provider.send(
            AlertNotification(
                title="Failed alert",
                price=10.0,
                estimated_value=20.0,
                expected_profit=10.0,
                flip_score=70,
                confidence=0.8,
                reasoning="Transport failure",
                listing_url="https://example.com/listing/999",
            )
        )

    assert webhook_url not in str(exc_info.value)
