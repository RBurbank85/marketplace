"""Persistent marketplace memory and the metrics derived from it.

PriceHistory is deliberately used as an *observation* log: a row is written on
every crawl, even when the price did not change.  This makes a missing price
change distinguishable from a listing that has not been seen again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Iterable, Optional
from uuid import UUID

from sqlmodel import Session, select

from database.database import get_session
from database.models import Listing, ListingStatus, PriceHistory


def _utc(value: Optional[datetime]) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _tokens(*values: Optional[str]) -> set[str]:
    return {
        token
        for value in values
        for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(token) > 1
    }


def _same_item(left: Listing, right: Listing) -> bool:
    """A conservative relist match: same source and materially same title."""
    if left.source.lower() != right.source.lower():
        return False
    if (
        left.seller_id is not None
        and right.seller_id is not None
        and left.seller_id != right.seller_id
    ):
        return False
    left_tokens = _tokens(left.title)
    right_tokens = _tokens(right.title)
    return bool(left_tokens) and left_tokens == right_tokens


@dataclass(frozen=True)
class PriceMetrics:
    initial_price: float
    current_price: float
    lowest_price: float
    highest_price: float
    observation_count: int
    change_count: int
    price_drop_count: int

    @property
    def has_price_changed(self) -> bool:
        return self.change_count > 0


@dataclass(frozen=True)
class SellerMetrics:
    seller_id: UUID
    listing_count: int
    comparable_listing_count: int
    underpriced_listing_count: int
    underpricing_rate: float
    is_frequently_underpricing: bool


@dataclass(frozen=True)
class ListingMetrics:
    listing_id: UUID
    observation_count: int
    has_seen_before: bool
    has_price_changed: bool
    price_drop_count: int
    days_on_market: float
    relisted_from_ids: tuple[UUID, ...]
    repeated_keywords: tuple[str, ...]
    similar_listings_average_days_to_sell: Optional[float]


@dataclass(frozen=True)
class ObservationResult:
    listing: Listing
    observation: PriceHistory
    is_new_listing: bool
    relisted_from_id: Optional[UUID]


class PriceHistoryService:
    """Records price observations and reports price movement for a listing."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url

    def observe(
        self,
        listing_id: UUID,
        price: float,
        observed_at: Optional[datetime] = None,
        *,
        session: Optional[Session] = None,
    ) -> PriceHistory:
        if price < 0:
            raise ValueError("price must be non-negative")
        if session is not None:
            return self._observe(session, listing_id, price, _utc(observed_at))
        with get_session(self.database_url) as managed_session:
            observation = self._observe(
                managed_session, listing_id, price, _utc(observed_at)
            )
            managed_session.commit()
            managed_session.refresh(observation)
            return observation

    def history(self, listing_id: UUID) -> list[PriceHistory]:
        with get_session(self.database_url) as session:
            statement = (
                select(PriceHistory)
                .where(PriceHistory.listing_id == listing_id)
                .order_by(PriceHistory.observed_at, PriceHistory.created_at)
            )
            return list(session.exec(statement).all())

    def metrics(self, listing_id: UUID) -> PriceMetrics:
        history = self.history(listing_id)
        if not history:
            raise LookupError(f"No price history exists for listing {listing_id}")
        prices = [entry.price for entry in history]
        changes = sum(
            previous != current for previous, current in zip(prices, prices[1:])
        )
        drops = sum(current < previous for previous, current in zip(prices, prices[1:]))
        return PriceMetrics(
            prices[0], prices[-1], min(prices), max(prices), len(prices), changes, drops
        )

    @staticmethod
    def _observe(
        session: Session, listing_id: UUID, price: float, observed_at: datetime
    ) -> PriceHistory:
        listing = session.get(Listing, listing_id)
        if listing is None:
            raise LookupError(f"Listing {listing_id} does not exist")
        listing.price = price
        listing.updated_at = observed_at
        observation = PriceHistory(
            price=price, observed_at=observed_at, listing_id=listing_id
        )
        session.add(listing)
        session.add(observation)
        session.flush()
        return observation


class SellerHistoryService:
    """Finds sellers whose listings are repeatedly cheap against like listings."""

    def __init__(
        self, database_url: Optional[str] = None, *, underprice_ratio: float = 0.85
    ) -> None:
        if not 0 < underprice_ratio <= 1:
            raise ValueError("underprice_ratio must be in (0, 1]")
        self.database_url = database_url
        self.underprice_ratio = underprice_ratio

    def metrics(
        self, seller_id: UUID, *, minimum_listings: int = 3, frequent_rate: float = 0.5
    ) -> SellerMetrics:
        with get_session(self.database_url) as session:
            seller_listings = list(
                session.exec(
                    select(Listing).where(Listing.seller_id == seller_id)
                ).all()
            )
            all_listings = list(session.exec(select(Listing)).all())

        comparable_count = 0
        underpriced_count = 0
        for listing in seller_listings:
            comparables = [
                other.price
                for other in all_listings
                if other.id != listing.id and _same_item(listing, other)
            ]
            if not comparables:
                continue
            comparable_count += 1
            if listing.price < median(comparables) * self.underprice_ratio:
                underpriced_count += 1
        rate = underpriced_count / comparable_count if comparable_count else 0.0
        frequent = (
            len(seller_listings) >= minimum_listings
            and comparable_count >= minimum_listings
            and rate >= frequent_rate
        )
        return SellerMetrics(
            seller_id,
            len(seller_listings),
            comparable_count,
            underpriced_count,
            rate,
            frequent,
        )


class ListingHistoryService:
    """Ingests listings, identifies relists, and produces listing-level memory."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url
        self.prices = PriceHistoryService(database_url)

    def observe(
        self, listing: Listing, observed_at: Optional[datetime] = None
    ) -> ObservationResult:
        """Persist an observation, updating an existing external listing when possible."""
        observed = _utc(observed_at)
        with get_session(self.database_url) as session:
            existing = self._find_exact(session, listing)
            relisted_from_id: Optional[UUID] = None
            is_new = existing is None
            if existing is None:
                previous = self._find_relist(session, listing)
                relisted_from_id = previous.id if previous is not None else None
                session.add(listing)
                session.flush()
                target = listing
            else:
                target = existing
                self._merge(target, listing)
            observation = self.prices.observe(
                target.id, listing.price, observed, session=session
            )  # type: ignore[arg-type]
            session.commit()
            session.refresh(target)
            session.refresh(observation)
            return ObservationResult(target, observation, is_new, relisted_from_id)

    def has_seen_before(self, listing: Listing) -> bool:
        with get_session(self.database_url) as session:
            return (
                self._find_exact(session, listing) is not None
                or self._find_relist(session, listing) is not None
            )

    def metrics(
        self, listing_id: UUID, *, as_of: Optional[datetime] = None
    ) -> ListingMetrics:
        now = _utc(as_of)
        with get_session(self.database_url) as session:
            listing = session.get(Listing, listing_id)
            if listing is None:
                raise LookupError(f"Listing {listing_id} does not exist")
            all_listings = list(session.exec(select(Listing)).all())
        price_metrics = self.prices.metrics(listing_id)
        history = self.prices.history(listing_id)
        last_seen = _utc(history[-1].observed_at if history else listing.updated_at)
        days_on_market = max(
            0.0, (last_seen - _utc(listing.created_at)).total_seconds() / 86400
        )
        relists = tuple(
            item.id
            for item in all_listings
            if item.id != listing.id
            and _same_item(listing, item)
            and _utc(item.created_at) < _utc(listing.created_at)
        )
        keywords = self._repeated_keywords(listing, all_listings)
        average = self._similar_average_days_to_sell(listing, all_listings, now)
        return ListingMetrics(
            listing.id,
            price_metrics.observation_count,
            price_metrics.observation_count > 1,
            price_metrics.has_price_changed,
            price_metrics.price_drop_count,
            days_on_market,
            relists,
            keywords,
            average,
        )

    @staticmethod
    def _find_exact(session: Session, listing: Listing) -> Optional[Listing]:
        if listing.external_id:
            return session.exec(
                select(Listing).where(
                    Listing.source == listing.source,
                    Listing.external_id == listing.external_id,
                )
            ).one_or_none()
        if listing.url:
            return session.exec(
                select(Listing).where(
                    Listing.source == listing.source, Listing.url == listing.url
                )
            ).one_or_none()
        return None

    @staticmethod
    def _find_relist(session: Session, listing: Listing) -> Optional[Listing]:
        candidates = list(
            session.exec(select(Listing).where(Listing.source == listing.source)).all()
        )
        matches = [
            candidate for candidate in candidates if _same_item(candidate, listing)
        ]
        return (
            max(matches, key=lambda candidate: candidate.created_at)
            if matches
            else None
        )

    @staticmethod
    def _merge(target: Listing, incoming: Listing) -> None:
        for name in ("title", "description", "url", "status", "seller_id", "search_id"):
            value = getattr(incoming, name)
            if value is not None:
                setattr(target, name, value)

    @staticmethod
    def _repeated_keywords(
        listing: Listing, listings: Iterable[Listing]
    ) -> tuple[str, ...]:
        target = _tokens(listing.title, listing.description)
        counts = {token: 0 for token in target}
        for other in listings:
            if other.id == listing.id:
                continue
            for token in target & _tokens(other.title, other.description):
                counts[token] += 1
        return tuple(sorted(token for token, count in counts.items() if count > 0))

    @staticmethod
    def _similar_average_days_to_sell(
        listing: Listing, listings: Iterable[Listing], now: datetime
    ) -> Optional[float]:
        durations: list[float] = []
        terminal = {ListingStatus.ARCHIVED, ListingStatus.WON, ListingStatus.PURCHASED}
        for other in listings:
            if (
                other.id == listing.id
                or other.status not in terminal
                or not _same_item(listing, other)
            ):
                continue
            end = min(_utc(other.updated_at), _utc(now))
            durations.append(
                max(0.0, (end - _utc(other.created_at)).total_seconds() / 86400)
            )
        return sum(durations) / len(durations) if durations else None


__all__ = [
    "ListingHistoryService",
    "ListingMetrics",
    "ObservationResult",
    "PriceHistoryService",
    "PriceMetrics",
    "SellerHistoryService",
    "SellerMetrics",
]
