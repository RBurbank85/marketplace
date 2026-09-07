from __future__ import annotations

import logging
import unicodedata
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.pipeline import BaseStage, PipelineContext, StageRegistry
from database.schemas import ListingCreate

logger = logging.getLogger(__name__)


def _normalize_price(raw_price: Any) -> Any:
    """Normalize common marketplace price formats without hiding invalid input."""
    if raw_price is None:
        return 0.0
    if isinstance(raw_price, (int, float)) and not isinstance(raw_price, bool):
        return float(raw_price)
    if not isinstance(raw_price, str):
        return raw_price

    price_text = raw_price.strip()
    if not price_text:
        return 0.0

    price_text = "".join(
        character
        for character in price_text
        if unicodedata.category(character) != "Sc"
    ).strip()

    if "," in price_text and "." in price_text:
        if price_text.rfind(",") > price_text.rfind("."):
            price_text = price_text.replace(".", "").replace(",", ".")
        else:
            price_text = price_text.replace(",", "")
    elif "," in price_text:
        comma_parts = price_text.split(",")
        if len(comma_parts) == 2 and len(comma_parts[1]) == 2:
            price_text = price_text.replace(",", ".")
        else:
            price_text = price_text.replace(",", "")

    try:
        return float(price_text)
    except ValueError:
        return price_text


class ListingPipelineData(BaseModel):
    """Data object flowing through the listing pipeline."""

    listing: Optional[ListingCreate] = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
    enriched_data: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)
    scoring_results: dict[str, Any] = Field(default_factory=dict)
    opportunity_results: dict[str, Any] = Field(default_factory=dict)
    listing_id: Optional[UUID] = None
    opportunity_id: Optional[UUID] = None


@StageRegistry.register("normalize")
class NormalizeStage(BaseStage[ListingPipelineData]):
    """Stage to normalize raw data into a ListingCreate object."""

    async def process(
        self, context: PipelineContext[ListingPipelineData]
    ) -> PipelineContext[ListingPipelineData]:
        raw = context.data.raw_data

        title = raw.get("title", "").strip()
        price = _normalize_price(raw.get("price"))

        source = raw.get("source", "unknown")
        url = raw.get("url", "")
        external_id = raw.get("external_id") or url

        context.data.listing = ListingCreate(
            title=title,
            price=price,
            source=source,
            url=url,
            external_id=external_id,
            description=raw.get("description"),
        )
        return context


@StageRegistry.register("validate")
class ValidateStage(BaseStage[ListingPipelineData]):
    """Stage to validate the normalized listing."""

    async def process(
        self, context: PipelineContext[ListingPipelineData]
    ) -> PipelineContext[ListingPipelineData]:
        listing = context.data.listing
        if not listing:
            context.terminate("No listing data to validate")
            return context

        if not listing.title:
            context.data.validation_errors.append("Title is missing")
        if listing.price <= 0:
            # We allow 0 if it's truly free, but usually it's a mistake or "contact for price"
            context.data.validation_errors.append("Price must be greater than zero")
            
        if context.data.validation_errors:
            context.terminate(f"Validation failed: {context.data.validation_errors}")
            
        return context


@StageRegistry.register("persist")
class PersistStage(BaseStage[ListingPipelineData]):
    """Stage to persist the listing to the database."""

    def __init__(self, name: str | None = None, repository: Any = None) -> None:
        super().__init__(name)
        self.repository = repository

    async def process(
        self, context: PipelineContext[ListingPipelineData]
    ) -> PipelineContext[ListingPipelineData]:
        if not context.data.listing:
            context.terminate("No listing to persist")
            return context

        if not self.repository:
             from database.repositories import ListingRepository
             self.repository = ListingRepository()

        try:
            existing = self.repository.get_by_external_id(context.data.listing.external_id)
            if existing:
                context.data.listing_id = existing.id
                logger.info(f"Listing {existing.external_id} already exists, skipping persistence")
            else:
                from database.models import Listing

                db_listing = self.repository.create(
                    Listing(**context.data.listing.model_dump())
                )
                context.data.listing_id = db_listing.id
                logger.info(f"Persisted listing: {db_listing.id}")
        except Exception as e:
            logger.error(f"Failed to persist listing: {e}")
            context.terminate(f"Persistence error: {e}")

        return context


@StageRegistry.register("valuate")
class ValuateStage(BaseStage[ListingPipelineData]):
    """Stage to perform market valuation."""

    async def process(
        self, context: PipelineContext[ListingPipelineData]
    ) -> PipelineContext[ListingPipelineData]:
        from analysis.valuation.estimator import estimate_value
        
        if not context.data.listing:
            return context
            
        listing_dict = context.data.listing.model_dump()
        valuation = estimate_value(listing_dict)
        context.data.enriched_data["market_value"] = valuation.get("estimated_value")
        context.data.enriched_data["valuation_confidence"] = valuation.get("confidence")
        
        return context


@StageRegistry.register("score")
class ScoreStage(BaseStage[ListingPipelineData]):
    """Stage to calculate FlipScore."""

    async def process(
        self, context: PipelineContext[ListingPipelineData]
    ) -> PipelineContext[ListingPipelineData]:
        from analysis.flipscore import evaluate_listing
        
        if not context.data.listing:
            return context
            
        listing_dict = context.data.listing.model_dump()
        listing_dict.update(context.data.enriched_data)
        
        scoring = evaluate_listing(listing_dict)
        context.data.scoring_results = scoring
        
        return context


@StageRegistry.register("opportunity")
class OpportunityDetectionStage(BaseStage[ListingPipelineData]):
    """Stage to detect hidden opportunities."""

    async def process(
        self, context: PipelineContext[ListingPipelineData]
    ) -> PipelineContext[ListingPipelineData]:
        from analysis.opportunity import analyze_opportunity
        
        if not context.data.listing:
            return context
            
        listing_dict = context.data.listing.model_dump()
        listing_dict["description"] = listing_dict.get("description") or ""
        listing_dict.update(context.data.enriched_data)
        listing_dict.update(context.data.scoring_results)
        
        opp_results = analyze_opportunity(listing_dict)
        context.data.opportunity_results = {
            "score": opp_results.opportunity_score,
            "explanation": opp_results.explanation,
        }
        
        return context


@StageRegistry.register("queue")
class QueueStage(BaseStage[ListingPipelineData]):
    """Stage to queue promising opportunities for review."""

    def __init__(
        self,
        name: str | None = None,
        opp_threshold: float = 70.0,
        score_threshold: float = 60.0,
        opportunity_repository: Any = None,
        database_url: str | None = None,
    ) -> None:
        super().__init__(name)
        self.opp_threshold = opp_threshold
        self.score_threshold = score_threshold
        self.opportunity_repository = opportunity_repository
        self.database_url = database_url

    async def process(
        self, context: PipelineContext[ListingPipelineData]
    ) -> PipelineContext[ListingPipelineData]:
        if not context.data.listing_id:
            return context
            
        opp_score = context.data.opportunity_results.get("score", 0)
        flip_score = context.data.scoring_results.get("score", 0)
        
        if opp_score >= self.opp_threshold or flip_score >= self.score_threshold:
            from database.repositories import OpportunityRepository
            from database.models import Opportunity
            
            opp_repo = self.opportunity_repository or OpportunityRepository(
                database_url=self.database_url
            )
            
            # Use raw model for creation as the repo expects the model instance or we can wrap it
            expected_profit = context.data.enriched_data.get("market_value", 0) - (
                context.data.listing.price if context.data.listing else 0
            )
            context.data.opportunity_results["expected_profit"] = expected_profit
            opp_model = Opportunity(
                listing_id=context.data.listing_id,
                potential_profit=max(0, expected_profit),
                confidence_score=context.data.scoring_results.get("confidence", 0.5),
                notes=context.data.opportunity_results.get("explanation")
            )
            
            db_opp = opp_repo.get_or_create_for_listing(opp_model)
            context.data.opportunity_id = db_opp.id
            logger.info(f"Queued opportunity: {db_opp.id}")
            
        return context


@StageRegistry.register("notify")
class NotifyStage(BaseStage[ListingPipelineData]):
    """Stage to notify about new opportunities."""

    def __init__(self, name: str | None = None, notification_service: Any = None) -> None:
        super().__init__(name)
        self.notification_service = notification_service

    async def process(
        self, context: PipelineContext[ListingPipelineData]
    ) -> PipelineContext[ListingPipelineData]:
        if not context.data.opportunity_id:
            return context

        if self.notification_service is None:
            return context

        from alerts.notifications import AlertNotification

        listing = context.data.listing
        if listing is None:
            return context

        alert = AlertNotification(
            title=listing.title,
            price=listing.price,
            estimated_value=context.data.enriched_data.get("market_value", 0.0),
            expected_profit=context.data.opportunity_results.get("expected_profit", 0.0),
            flip_score=int(context.data.scoring_results.get("score", 0)),
            confidence=float(context.data.scoring_results.get("confidence", 0.0)),
            reasoning=context.data.opportunity_results.get("explanation", ""),
            listing_url=listing.url or "",
        )
        logger.info(f"Notification triggered for opportunity {context.data.opportunity_id}")
        self.notification_service.send(alert)
        
        return context
