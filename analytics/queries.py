"""Read-only reporting queries for the DuckDB analytics warehouse."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from analytics.warehouse import Warehouse


def _rows(sql: str, warehouse_path: str | Path | None = None) -> list[dict[str, Any]]:
    connection = Warehouse(warehouse_path=warehouse_path).connect()
    try:
        result = connection.execute(sql)
        columns = [column[0] for column in result.description]
        return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    finally:
        connection.close()


def most_profitable_categories(
    warehouse_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT category, COUNT(*) AS listing_count, SUM(expected_profit) AS total_expected_profit,
               AVG(expected_profit) AS average_expected_profit
        FROM listing_facts WHERE category IS NOT NULL AND expected_profit IS NOT NULL
        GROUP BY category ORDER BY total_expected_profit DESC
    """,
        warehouse_path,
    )


def average_flipscore(warehouse_path: str | Path | None = None) -> list[dict[str, Any]]:
    rows = _rows(
        "SELECT AVG(flip_score) AS average_flipscore FROM listing_facts WHERE flip_score IS NOT NULL",
        warehouse_path,
    )
    return rows if rows and rows[0]["average_flipscore"] is not None else []


def median_asking_prices(
    warehouse_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT category, MEDIAN(asking_price) AS median_asking_price, COUNT(*) AS listing_count
        FROM listing_facts WHERE asking_price IS NOT NULL
        GROUP BY category ORDER BY median_asking_price DESC
    """,
        warehouse_path,
    )


def price_reductions(warehouse_path: str | Path | None = None) -> list[dict[str, Any]]:
    return _rows(
        """
        WITH changes AS (
            SELECT listing_id, price, observed_at,
                   LAG(price) OVER (PARTITION BY listing_id ORDER BY observed_at) AS previous_price
            FROM price_history
        )
        SELECT listing_id, observed_at, previous_price, price AS new_price,
               previous_price - price AS reduction_amount
        FROM changes WHERE price < previous_price ORDER BY observed_at DESC
    """,
        warehouse_path,
    )


def seller_frequency(warehouse_path: str | Path | None = None) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT seller_id, seller_name, COUNT(*) AS listing_count
        FROM listing_facts WHERE seller_id IS NOT NULL
        GROUP BY seller_id, seller_name ORDER BY listing_count DESC, seller_name
    """,
        warehouse_path,
    )


def keyword_performance(
    warehouse_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Aggregate persisted search keywords; no keyword scoring is recomputed."""
    return _rows(
        """
        SELECT search_query AS keyword, COUNT(*) AS listing_count,
               AVG(keyword_score) AS average_keyword_score,
               AVG(expected_profit) AS average_expected_profit
        FROM listing_facts WHERE search_query IS NOT NULL
        GROUP BY search_query ORDER BY average_expected_profit DESC NULLS LAST, listing_count DESC
    """,
        warehouse_path,
    )


def category_trends(warehouse_path: str | Path | None = None) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT CAST(CAST(listed_at AS DATE) AS VARCHAR) AS day, category, COUNT(*) AS listing_count,
               AVG(expected_profit) AS average_expected_profit
        FROM listing_facts WHERE listed_at IS NOT NULL AND category IS NOT NULL
        GROUP BY day, category ORDER BY day, category
    """,
        warehouse_path,
    )


def daily_listing_volume(
    warehouse_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT CAST(CAST(listed_at AS DATE) AS VARCHAR) AS day, COUNT(*) AS listing_count
        FROM listing_facts WHERE listed_at IS NOT NULL GROUP BY day ORDER BY day
    """,
        warehouse_path,
    )
