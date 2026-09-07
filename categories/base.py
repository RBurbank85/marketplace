"""Shared schema for marketplace category knowledge plugins."""

from __future__ import annotations

from dataclasses import dataclass

from core.plugins import CategoryPlugin


@dataclass(frozen=True)
class MarginRange:
    """Expected gross-margin range before marketplace fees and labor."""

    low: float
    high: float

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2


@dataclass(frozen=True)
class ShippingProfile:
    """Handling guidance used by listing and fulfillment workflows."""

    size: str
    method: str
    risk_notes: str


class CategoryKnowledge(CategoryPlugin):
    """Base class for a self-contained category knowledge module.

    Subclasses are discovered by :class:`core.plugins.PluginLoader`.  Keeping
    the knowledge as class attributes makes modules easy to review and avoids
    a central category switchboard.
    """

    slug: str = ""
    brands: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    common_misspellings: tuple[str, ...] = ()
    seasonality: str = "Year-round; monitor local demand."
    seasonality_months: tuple[int, ...] = ()
    repair_opportunities: tuple[str, ...] = ()
    shipping_profile: ShippingProfile = ShippingProfile(
        "unknown", "review", "No profile provided."
    )
    typical_margins: MarginRange = MarginRange(0.0, 0.0)
    pricing_providers: tuple[str, ...] = ()
    common_model_prefixes: tuple[str, ...] = ()
    related_categories: tuple[str, ...] = ()

    @property
    def category(self) -> str:
        return self.slug or self.name

    def matches(self, text: str) -> list[str]:
        """Return category signals present in normalized listing text."""
        from analysis.valuation.parser import normalize_title

        normalized = normalize_title(text)
        signals = (
            *self.keywords,
            *self.brands,
            *self.common_misspellings,
            *self.common_model_prefixes,
        )
        return [signal for signal in signals if normalize_title(signal) in normalized]
