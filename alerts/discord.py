from __future__ import annotations

from typing import Any, Callable

import httpx

from alerts.notifications import AlertNotification, Notification


class DiscordNotificationError(RuntimeError):
    """Raised when a Discord webhook notification cannot be delivered."""


class DiscordNotification(Notification):
    """Send alerts to a Discord webhook endpoint."""

    name = "discord"

    def __init__(
        self,
        webhook_url: str | None = None,
        http_client: Callable[[str, dict[str, Any]], None] | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.webhook_url = self._validate_webhook_url(webhook_url)
        self._timeout = timeout
        self._transport = transport
        self._http_client = http_client or self._post_json

    def send(self, alert: AlertNotification) -> None:
        if not self.webhook_url:
            return

        payload = self._build_payload(alert)
        self._http_client(self.webhook_url, payload)

    def _build_payload(self, alert: AlertNotification) -> dict[str, Any]:
        return {
            "content": f"New flip opportunity: {alert.title}",
            "embeds": [
                {
                    "title": alert.title,
                    "description": alert.reasoning,
                    "color": 3066993,
                    "fields": [
                        {
                            "name": "Price",
                            "value": self._money(alert.price),
                            "inline": True,
                        },
                        {
                            "name": "Estimated value",
                            "value": self._money(alert.estimated_value),
                            "inline": True,
                        },
                        {
                            "name": "Expected profit",
                            "value": self._money(alert.expected_profit),
                            "inline": True,
                        },
                        {
                            "name": "FlipScore",
                            "value": str(alert.flip_score),
                            "inline": True,
                        },
                        {
                            "name": "Confidence",
                            "value": f"{alert.confidence:.0%}",
                            "inline": True,
                        },
                        {
                            "name": "Reasoning",
                            "value": alert.reasoning,
                            "inline": False,
                        },
                        {
                            "name": "Listing URL",
                            "value": alert.listing_url,
                            "inline": False,
                        },
                    ],
                }
            ],
        }

    @staticmethod
    def _money(value: float) -> str:
        return f"${value:,.2f}"

    @staticmethod
    def _validate_webhook_url(webhook_url: str | None) -> str | None:
        if webhook_url is None or not webhook_url.strip():
            return None

        normalized = webhook_url.strip()
        if not (
            normalized.startswith("https://discord.com/api/webhooks/")
            or normalized.startswith("https://discordapp.com/api/webhooks/")
        ):
            raise ValueError(
                "Discord webhook must be a valid Discord webhook URL"
            )
        return normalized

    def _post_json(self, url: str, payload: dict[str, Any]) -> None:
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout,
            ) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DiscordNotificationError(
                "Unable to send Discord notification"
            ) from exc
