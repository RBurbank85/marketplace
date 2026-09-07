from __future__ import annotations

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from app.main import app
from analytics.dashboard import dashboard_data
from analytics.queries import (
    average_flipscore,
    daily_listing_volume,
    most_profitable_categories,
    price_reductions,
    seller_frequency,
)
from analytics.warehouse import Warehouse, sync_operational_data


def _operational_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE sellers (id TEXT PRIMARY KEY, name TEXT);
            CREATE TABLE searches (id TEXT PRIMARY KEY, query TEXT);
            CREATE TABLE listings (
                id TEXT PRIMARY KEY, title TEXT, price REAL, created_at TEXT,
                seller_id TEXT, search_id TEXT, category TEXT, flip_score REAL,
                keyword_score REAL
            );
            CREATE TABLE opportunities (
                id TEXT PRIMARY KEY, listing_id TEXT, potential_profit REAL, confidence_score REAL
            );
            CREATE TABLE price_history (id TEXT PRIMARY KEY, listing_id TEXT, price REAL, observed_at TEXT);
            INSERT INTO sellers VALUES ('seller-1', 'Frequent seller');
            INSERT INTO searches VALUES ('search-1', 'nintendo switch');
            INSERT INTO listings VALUES
                ('listing-1', 'Nintendo Switch', 250, '2026-07-01 12:00:00', 'seller-1', 'search-1', 'games', 80, 90),
                ('listing-2', 'Used game', 100, '2026-07-01 15:00:00', 'seller-1', 'search-1', 'games', 60, 70);
            INSERT INTO opportunities VALUES ('opportunity-1', 'listing-1', 75, .9);
            INSERT INTO price_history VALUES
                ('price-1', 'listing-1', 300, '2026-06-30 12:00:00'),
                ('price-2', 'listing-1', 250, '2026-07-01 12:00:00');
        """)


def test_sync_creates_read_only_analytics_snapshot(tmp_path: Path) -> None:
    operational = tmp_path / "operational.db"
    warehouse = tmp_path / "analytics.duckdb"
    _operational_database(operational)

    result = sync_operational_data(operational, warehouse)

    assert result.tables["listings"] == 2
    assert most_profitable_categories(warehouse) == [
        {
            "category": "games",
            "listing_count": 1,
            "total_expected_profit": 75.0,
            "average_expected_profit": 75.0,
        }
    ]
    assert average_flipscore(warehouse) == [{"average_flipscore": 70.0}]
    assert seller_frequency(warehouse)[0]["listing_count"] == 2
    assert price_reductions(warehouse)[0]["reduction_amount"] == 50.0
    assert daily_listing_volume(warehouse) == [
        {"day": "2026-07-01", "listing_count": 2}
    ]

    connection = Warehouse(warehouse).connect()
    try:
        try:
            connection.execute("CREATE TABLE must_not_write (id INTEGER)")
        except Exception:
            pass
        else:
            raise AssertionError("Analytics connections must be read-only")
    finally:
        connection.close()


def test_dashboard_exposes_all_analytics_panels(tmp_path: Path) -> None:
    operational = tmp_path / "operational.db"
    warehouse = tmp_path / "analytics.duckdb"
    _operational_database(operational)
    sync_operational_data(operational, warehouse)

    report = dashboard_data(warehouse)

    assert set(report) == {
        "most_profitable_categories",
        "average_flipscore",
        "median_asking_prices",
        "price_reductions",
        "seller_frequency",
        "keyword_performance",
        "category_trends",
        "daily_listing_volume",
    }


def test_empty_operational_database_exposes_empty_dashboard(tmp_path: Path) -> None:
    operational = tmp_path / "empty.db"
    warehouse = tmp_path / "analytics.duckdb"
    sqlite3.connect(operational).close()

    sync_operational_data(operational, warehouse)

    report = dashboard_data(warehouse)

    assert set(report) == {
        "most_profitable_categories",
        "average_flipscore",
        "median_asking_prices",
        "price_reductions",
        "seller_frequency",
        "keyword_performance",
        "category_trends",
        "daily_listing_volume",
    }
    assert all(panel == [] for panel in report.values())


def test_repeated_snapshot_refresh_does_not_duplicate_rows(tmp_path: Path) -> None:
    operational = tmp_path / "operational.db"
    warehouse = tmp_path / "analytics.duckdb"
    _operational_database(operational)

    first = sync_operational_data(operational, warehouse)
    second = sync_operational_data(operational, warehouse)

    assert first.tables["listings"] == 2
    assert second.tables["listings"] == 2
    with Warehouse(warehouse).connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 2
        assert (
            connection.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
            == 2
        )


def test_cli_sync_supports_temporary_paths(tmp_path: Path) -> None:
    operational = tmp_path / "operational.db"
    warehouse = tmp_path / "analytics.duckdb"
    _operational_database(operational)

    result = CliRunner().invoke(
        app,
        [
            "analytics",
            "sync",
            "--database-url",
            str(operational),
            "--warehouse-path",
            str(warehouse),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Analytics snapshot refreshed" in result.stdout
    assert most_profitable_categories(warehouse)[0]["listing_count"] == 1
