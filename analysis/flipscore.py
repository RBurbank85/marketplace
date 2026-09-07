from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from analysis.keywords import keyword_score
from categories import get_category
from config.settings import settings


@dataclass(frozen=True)
class ComponentResult:
    """Outcome of an individual scoring component."""

    name: str
    score: float  # 0 to 100
    explanation: str


class ScoreComponent:
    """Base interface for an individual FlipScore component."""

    name = "component"
    description = "Base scoring component"

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        raise NotImplementedError


class PriceScore(ScoreComponent):
    """Evaluates the listing price relative to market expectations."""

    name = "price"
    description = "Rewards lower prices as they increase profit potential."

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        price = float(listing.get("price", 0) or 0)
        if price <= 0:
            return ComponentResult(self.name, 0, "Price is missing or invalid.")
        if price < 100:
            return ComponentResult(
                self.name, 100, "Price is very low, maximizing profit room."
            )
        if price < 200:
            return ComponentResult(
                self.name, 80, "Price is low, supporting healthy margins."
            )
        if price < 400:
            return ComponentResult(self.name, 50, "Price is moderate but manageable.")
        if price < 1000:
            return ComponentResult(
                self.name, 30, "Price is high, narrowing potential margins."
            )
        return ComponentResult(
            self.name, 10, "Price is very high, significantly compressing margin."
        )


class DemandScore(ScoreComponent):
    """Estimates market demand based on category, keywords, and brand."""

    name = "demand"
    description = "High demand improves liquidity and resale speed."

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        category = str(listing.get("category", "") or "").strip().lower()
        knowledge = get_category(category)

        keyword_val = listing.get("keyword_score")
        if keyword_val is None:
            text = " ".join(
                [
                    str(listing.get("title", "") or ""),
                    str(listing.get("description", "") or ""),
                ]
            ).strip()
            keyword_val = keyword_score(text) if text else 0

        brand_val = float(listing.get("brand_score", 0) or 0)

        # Combine signals
        score = 0.0
        reasons = []

        if knowledge and knowledge.typical_margins.midpoint >= 0.25:
            score += 40
            reasons.append(f"Category '{category}' has historically strong demand.")
        elif knowledge:
            score += 20
            reasons.append(f"Category '{category}' has moderate demand signals.")

        if keyword_val >= 70:
            score += 40
            reasons.append(
                "High-value keywords suggest strong alignment with buyer intent."
            )
        elif keyword_val >= 40:
            score += 20
            reasons.append("Moderate keyword matches indicate reasonable demand.")

        if brand_val >= 80:
            score += 20
            reasons.append("Strong brand recognition boosts resale confidence.")
        elif brand_val >= 50:
            score += 10
            reasons.append("Decent brand presence adds some value.")

        final_score = min(100, score)
        explanation = (
            " ".join(reasons) if reasons else "No clear demand signals were detected."
        )
        return ComponentResult(self.name, final_score, explanation)


class SellerScore(ScoreComponent):
    """Evaluates seller factors like motivation and listing freshness."""

    name = "seller"
    description = "Motivated sellers and fresh listings often lead to better deals."

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        motivation = str(listing.get("seller_motivation", "") or "").strip().lower()
        age = float(listing.get("listing_age", 999) or 999)

        score = 50.0  # Neutral starting point
        reasons = []

        if any(
            term in motivation
            for term in ["must sell", "urgent", "moving", "cash", "urgently"]
        ):
            score += 30
            reasons.append("Seller appears highly motivated.")
        elif motivation:
            score += 10
            reasons.append("Seller motivation is present.")

        if age <= 2:
            score += 20
            reasons.append("Listing is very fresh, suggesting high availability.")
        elif age <= 7:
            score += 10
            reasons.append("Listing is relatively recent.")
        else:
            score -= 10
            reasons.append("Listing is older and may be stale.")

        final_score = max(0, min(100, score))
        explanation = " ".join(reasons) if reasons else "Seller signals are neutral."
        return ComponentResult(self.name, final_score, explanation)


class RiskScore(ScoreComponent):
    """Assesses potential risks like fraud, condition issues, or lack of info."""

    name = "risk"
    description = (
        "Higher risk scores indicate lower overall safety/confidence in the flip."
    )

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        # We'll invert this: 100 is low risk (safe), 0 is high risk (danger)
        repair_indicators = listing.get("repair_indicators", []) or []
        if isinstance(repair_indicators, str):
            repair_indicators = [repair_indicators]

        has_suspicious_terms = any(
            term in str(listing.get("description", "")).lower()
            for term in ["no returns", "as is", "untested"]
        )

        score = 80.0  # Start relatively safe
        reasons = []

        if repair_indicators:
            score -= 30
            reasons.append("Known repair issues increase implementation risk.")

        if has_suspicious_terms:
            score -= 20
            reasons.append("Seller terms ('as-is', 'untested') increase risk.")

        if not listing.get("description"):
            score -= 10
            reasons.append("Lack of listing description increases uncertainty.")

        final_score = max(0, min(100, score))
        explanation = (
            " ".join(reasons) if reasons else "No major risk factors detected."
        )
        return ComponentResult(self.name, final_score, explanation)


class DistanceScore(ScoreComponent):
    """Evaluates the logistical cost and effort of acquisition."""

    name = "distance"
    description = "Proximity reduces overhead and increases the likelihood of a successful pickup."

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        distance = float(listing.get("distance", 999) or 999)
        if distance <= 5:
            return ComponentResult(
                self.name, 100, "Very close; acquisition is highly convenient."
            )
        if distance <= 15:
            return ComponentResult(
                self.name, 75, "Reasonable distance; acquisition is practical."
            )
        if distance <= 30:
            return ComponentResult(
                self.name, 40, "Significant distance; increases acquisition overhead."
            )
        return ComponentResult(
            self.name, 10, "Far distance; acquisition may be impractical."
        )


class RepairScore(ScoreComponent):
    """Specifically evaluates the difficulty and impact of required repairs."""

    name = "repair"
    description = (
        "Items needing repair are higher effort but may offer steeper discounts."
    )

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        indicators = listing.get("repair_indicators", []) or []
        if isinstance(indicators, str):
            indicators = [indicators]

        if not indicators:
            return ComponentResult(self.name, 100, "No repair issues detected.")

        text = " ".join([str(i).lower() for i in indicators])
        if any(kw in text for kw in ["broken", "shattered", "water", "parts"]):
            return ComponentResult(
                self.name, 20, "Significant repairs likely required."
            )
        if any(kw in text for kw in ["battery", "cracked", "scratched", "worn"]):
            return ComponentResult(
                self.name, 50, "Minor or cosmetic repairs may be needed."
            )

        return ComponentResult(
            self.name, 70, "Unknown or ambiguous repair indicators present."
        )


class SeasonalityScore(ScoreComponent):
    """Estimates how much current seasonal trends affect this item's value."""

    name = "seasonality"
    description = "Items sold in-season usually command higher prices and faster sales."

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        months = listing.get("seasonality_months")
        if months is None:
            category = get_category(str(listing.get("category", "") or ""))
            months = category.seasonality_months if category else ()

        valid_months = {
            int(month)
            for month in (months or ())
            if str(month).isdigit() and 1 <= int(month) <= 12
        }
        if not valid_months:
            return ComponentResult(
                self.name, 50, "No seasonal data is available; the score is neutral."
            )

        month = listing.get("current_month")
        if month is None:
            month = datetime.now(timezone.utc).month
        try:
            month = int(month)
        except (TypeError, ValueError):
            return ComponentResult(
                self.name, 50, "Current month is invalid; the seasonal score is neutral."
            )
        if not 1 <= month <= 12:
            return ComponentResult(
                self.name, 50, "Current month is invalid; the seasonal score is neutral."
            )
        if month in valid_months:
            return ComponentResult(
                self.name, 80, f"Month {month} is in the category's seasonal demand window."
            )
        return ComponentResult(
            self.name, 20, f"Month {month} is outside the category's seasonal demand window."
        )


class ConfidenceScore(ScoreComponent):
    """Measures the quality and quantity of data used to generate the score."""

    name = "confidence"
    description = "Higher confidence indicates more reliable data signals."

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        field_count = sum(
            1
            for key in listing
            if listing.get(key) not in (None, "", [], {}, ())
            and key not in {"title", "description"}
        )

        # Scale 0 to 100
        score = min(100, 20 + (field_count * 10))

        explanation = f"Calculated based on {field_count} active data fields."
        return ComponentResult(self.name, score, explanation)


class CompetitionScore(ScoreComponent):
    """Estimates how much competition exists for this listing/category."""

    name = "competition"
    description = "Lower competition means you have more time and leverage."

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        # Placeholder: could be based on listing views, or how many other similar listings exist
        views = int(listing.get("view_count", 0) or 0)
        if views > 100:
            return ComponentResult(
                self.name, 20, "High view count suggests high competition."
            )
        if views > 20:
            return ComponentResult(
                self.name, 60, "Moderate view count suggests some interest."
            )
        return ComponentResult(
            self.name,
            90,
            "Low view count suggests a potentially overlooked opportunity.",
        )


class HistoricalScore(ScoreComponent):
    """Compares the listing against historical performance data."""

    name = "historical"
    description = "Items with strong historical flip performance are rated higher."

    def calculate(self, listing: dict[str, Any]) -> ComponentResult:
        outcomes = listing.get("historical_outcomes")
        if not isinstance(outcomes, (list, tuple)):
            outcomes = []

        margins = []
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            purchase_price = outcome.get("purchase_price", outcome.get("buy_price"))
            sale_price = outcome.get("sale_price", outcome.get("resale_price"))
            try:
                purchase_price = float(purchase_price)
                sale_price = float(sale_price)
            except (TypeError, ValueError):
                continue
            if purchase_price > 0 and sale_price >= 0:
                margins.append((sale_price - purchase_price) / purchase_price)

        if not margins:
            return ComponentResult(
                self.name, 50, "No historical sale outcomes are available; the score is neutral."
            )

        average_margin = sum(margins) / len(margins)
        score = max(0.0, min(100.0, 50.0 + average_margin * 100.0))
        if score >= 70:
            explanation = f"Historical outcomes show strong average gross margin ({average_margin:.0%})."
        elif score <= 30:
            explanation = f"Historical outcomes show weak average gross margin ({average_margin:.0%})."
        else:
            explanation = f"Historical outcomes show moderate average gross margin ({average_margin:.0%})."
        return ComponentResult(self.name, score, explanation)


class ScoringPipeline:
    """Combines multiple score components using configurable weights."""

    def __init__(
        self, components: list[ScoreComponent], weights: dict[str, float] | None = None
    ):
        self.components = components
        self.weights = weights or {c.name: 1.0 for c in components}

    def evaluate(self, listing: dict[str, Any]) -> dict[str, Any]:
        results = {}
        total_weighted_score = 0.0
        total_weight = 0.0

        for component in self.components:
            res = component.calculate(listing)
            weight = self.weights.get(component.name, 1.0)

            results[component.name] = {
                "score": res.score,
                "explanation": res.explanation,
                "weight": weight,
            }

            total_weighted_score += res.score * weight
            total_weight += weight

        overall_score = total_weighted_score / total_weight if total_weight > 0 else 0
        overall_score = max(0.0, min(100.0, overall_score))

        # Confidence is special, it's one of the components but also a top-level return
        confidence_res = results.get("confidence", {"score": 50})
        confidence = confidence_res["score"] / 100.0

        return {
            "score": int(round(overall_score)),
            "confidence": round(confidence, 2),
            "component_scores": results,
            "reasons": [
                res["explanation"] for res in results.values() if res["explanation"]
            ],
        }


DEFAULT_COMPONENTS = [
    PriceScore(),
    DemandScore(),
    SellerScore(),
    RiskScore(),
    DistanceScore(),
    RepairScore(),
    SeasonalityScore(),
    ConfidenceScore(),
    CompetitionScore(),
    HistoricalScore(),
]

# We will load these from settings in the evaluate_listing function
DEFAULT_WEIGHTS = {
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
}


def evaluate_listing(
    listing: dict[str, Any],
    components: list[ScoreComponent] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Evaluate a listing using the modular scoring pipeline."""

    comp_list = components or DEFAULT_COMPONENTS
    weight_dict = weights or settings.flipscore_weights or DEFAULT_WEIGHTS

    pipeline = ScoringPipeline(comp_list, weight_dict)
    return pipeline.evaluate(listing)


def calculate(listing: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible wrapper around the modular evaluator."""

    return evaluate_listing(listing)
