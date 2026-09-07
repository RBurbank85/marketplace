# MAIE domain model

## Overview

The core domain model for MAIE is centered around listings discovered from marketplace sources. Each listing can be associated with a seller, a search context, zero or more images, historical prices, opportunities, and optionally a purchase record.

## Core entities

- Listing: the primary item under review. It stores source-specific metadata, current price, and status.
- Seller: the marketplace seller connected to a listing, with optional profile metadata.
- Image: one or more images attached to a listing.
- PriceHistory: snapshots of listing prices over time.
- Search: the search or collection context that surfaced the listing.
- Opportunity: a calculated arbitrage or profit opportunity tied to a listing.
- Queue: the manual-review record for an opportunity; it must be approved before notification.
- Purchase: the final acquisition record for a listing when it has been purchased.

## FlipScore input contracts

- `CategoryKnowledge.seasonality_months` is an optional tuple of month numbers
	(1-12). A listing may provide the same field directly, plus `current_month`
	for deterministic evaluation. Missing or invalid seasonal data produces a
	score of 50 with an explicit neutral explanation.
- `historical_outcomes` is an optional list of completed sale mappings. Each
	mapping requires a positive `purchase_price` (or `buy_price`) and
	`sale_price` (or `resale_price`). Historical scoring uses the average realized
	gross margin; malformed or absent outcomes produce a score of 50 and an
	explicit neutral explanation. Outcomes should be filtered to comparable items
	before scoring.

## Design principles

- UUID primary keys are used for distributed-safe identity and to avoid integer-based collisions.
- Every model includes created_at and updated_at timestamps for auditability.
- SQLModel is used for persistence, while Pydantic models can be introduced later for API payload validation if needed.
- Relationships are modeled explicitly so the graph is queryable and intuitive.
- Common query fields are indexed to preserve read performance.

## Notes

The initial implementation keeps persistence models and business logic separate by placing database entities in the database package and leaving application services free to compose them.
