"""DuckDB warehouse snapshots sourced from the operational SQLite database.

The SQLite connection is opened in read-only mode.  DuckDB is deliberately a
separate, replaceable reporting store: it is the only database this module
writes while synchronising.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

import duckdb


from analytics.sync import SyncManager, SyncMetrics


ANALYTICS_DIR = Path(__file__).resolve().parent
DEFAULT_WAREHOUSE_PATH = ANALYTICS_DIR / "warehouse.duckdb"
DEFAULT_OPERATIONAL_PATH = ANALYTICS_DIR.parent / "database" / "listings.db"
_INITIALIZATION_LOCK = threading.Lock()
_INITIALIZED_WAREHOUSES: set[Path] = set()


@dataclass(frozen=True)
class SyncResult:
    """The tables and row counts copied into a warehouse snapshot."""

    warehouse_path: Path
    tables: dict[str, int]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _duckdb_type(sqlite_type: str | None) -> str:
    declared = (sqlite_type or "").upper()
    if "INT" in declared:
        return "BIGINT"
    if any(
        token in declared for token in ("REAL", "FLOA", "DOUB", "NUMERIC", "DECIMAL")
    ):
        return "DOUBLE"
    if "BOOL" in declared:
        return "BOOLEAN"
    if "BLOB" in declared:
        return "BLOB"
    return "VARCHAR"


def _operational_connection(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"Operational SQLite database does not exist: {path}")
    # mode=ro guarantees analytics cannot change the operational database.
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _sqlite_tables(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({_quote(table)})")}


def _copy_table(
    source: sqlite3.Connection, target: duckdb.DuckDBPyConnection, table: str
) -> int:
    schema = source.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    definitions = ", ".join(
        f"{_quote(column[1])} {_duckdb_type(column[2])}" for column in schema
    )
    target.execute(f"CREATE TABLE {_quote(table)} ({definitions})")
    rows = source.execute(f"SELECT * FROM {_quote(table)}").fetchall()
    if rows:
        placeholders = ", ".join("?" for _ in schema)
        target.executemany(f"INSERT INTO {_quote(table)} VALUES ({placeholders})", rows)
    return len(rows)


def _column(
    columns: set[str], name: str, *, table: str = "l", type_name: str = "VARCHAR"
) -> str:
    return f"{table}.{_quote(name)}" if name in columns else f"NULL::{type_name}"


def _create_analytics_views(
    source: sqlite3.Connection, target: duckdb.DuckDBPyConnection
) -> None:
    """Create a stable projection of persisted operational facts.

    Category and scores come from columns on ``listings``. Expected profit is
    the sum of persisted ``opportunities.potential_profit`` rows; no business
    metrics are recalculated during synchronization.
    """
    tables = set(_sqlite_tables(source))
    if "listings" not in tables:
        target.execute(
            """
            CREATE VIEW listing_facts AS
            SELECT
                CAST(NULL AS VARCHAR) AS listing_id,
                CAST(NULL AS VARCHAR) AS title,
                CAST(NULL AS DOUBLE) AS asking_price,
                CAST(NULL AS VARCHAR) AS listed_at,
                CAST(NULL AS VARCHAR) AS source,
                CAST(NULL AS VARCHAR) AS seller_id,
                CAST(NULL AS VARCHAR) AS seller_name,
                CAST(NULL AS VARCHAR) AS search_id,
                CAST(NULL AS VARCHAR) AS search_query,
                CAST(NULL AS VARCHAR) AS category,
                CAST(NULL AS DOUBLE) AS flip_score,
                CAST(NULL AS DOUBLE) AS keyword_score,
                CAST(NULL AS DOUBLE) AS expected_profit,
                CAST(NULL AS DOUBLE) AS opportunity_confidence
            WHERE FALSE
            """
        )
        return

    listing_columns = _columns(source, "listings")
    seller_columns = _columns(source, "sellers") if "sellers" in tables else set()
    search_columns = _columns(source, "searches") if "searches" in tables else set()
    opportunity_columns = (
        _columns(source, "opportunities") if "opportunities" in tables else set()
    )

    seller_join = (
        "LEFT JOIN sellers s ON l.seller_id = s.id"
        if "sellers" in tables and "seller_id" in listing_columns
        else ""
    )
    search_join = (
        "LEFT JOIN searches se ON l.search_id = se.id"
        if "searches" in tables and "search_id" in listing_columns
        else ""
    )
    if not seller_join:
        seller_columns = set()
    if not search_join:
        search_columns = set()
    if "opportunities" in tables and "listing_id" in opportunity_columns:
        opportunity_join = """LEFT JOIN (
            SELECT listing_id, SUM(potential_profit) AS expected_profit,
                   AVG(confidence_score) AS opportunity_confidence
            FROM opportunities GROUP BY listing_id
        ) o ON l.id = o.listing_id"""
    else:
        opportunity_join = ""
    opportunity_projection = (
        "o.expected_profit, o.opportunity_confidence"
        if opportunity_join
        else "NULL::DOUBLE AS expected_profit, NULL::DOUBLE AS opportunity_confidence"
    )

    target.execute(
        f"""
        CREATE VIEW listing_facts AS
        SELECT
            {_column(listing_columns, "id")} AS listing_id,
            {_column(listing_columns, "title")} AS title,
            {_column(listing_columns, "price", type_name="DOUBLE")} AS asking_price,
            {_column(listing_columns, "created_at")} AS listed_at,
            {_column(listing_columns, "source")} AS source,
            {_column(listing_columns, "seller_id")} AS seller_id,
            {_column(seller_columns, "name", table="s")} AS seller_name,
            {_column(listing_columns, "search_id")} AS search_id,
            {_column(search_columns, "query", table="se")} AS search_query,
            {_column(listing_columns, "category")} AS category,
            {_column(listing_columns, "flip_score", type_name="DOUBLE")} AS flip_score,
            {_column(listing_columns, "keyword_score", type_name="DOUBLE")} AS keyword_score,
            {opportunity_projection}
        FROM listings l
        {seller_join}
        {search_join}
        {opportunity_join}
        """
    )


def _ensure_listing_facts_view(target: duckdb.DuckDBPyConnection) -> None:
    """Rebuild the reporting view from the current warehouse snapshot if it is missing."""
    has_view = target.execute(
        "SELECT COUNT(*) FROM information_schema.views WHERE table_name = 'listing_facts'"
    ).fetchone()[0]
    if has_view:
        return

    tables = {
        row[0]
        for row in target.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    if "listings" not in tables:
        target.execute(
            """
            CREATE VIEW listing_facts AS
            SELECT
                CAST(NULL AS VARCHAR) AS listing_id,
                CAST(NULL AS VARCHAR) AS title,
                CAST(NULL AS DOUBLE) AS asking_price,
                CAST(NULL AS VARCHAR) AS listed_at,
                CAST(NULL AS VARCHAR) AS source,
                CAST(NULL AS VARCHAR) AS seller_id,
                CAST(NULL AS VARCHAR) AS seller_name,
                CAST(NULL AS VARCHAR) AS search_id,
                CAST(NULL AS VARCHAR) AS search_query,
                CAST(NULL AS VARCHAR) AS category,
                CAST(NULL AS DOUBLE) AS flip_score,
                CAST(NULL AS DOUBLE) AS keyword_score,
                CAST(NULL AS DOUBLE) AS expected_profit,
                CAST(NULL AS DOUBLE) AS opportunity_confidence
            WHERE FALSE
            """
        )
        return

    listing_columns = {
        row[0] for row in target.execute("DESCRIBE listings").fetchall()
    }
    seller_columns = {row[0] for row in target.execute("DESCRIBE sellers").fetchall()} if "sellers" in tables else set()
    search_columns = {row[0] for row in target.execute("DESCRIBE searches").fetchall()} if "searches" in tables else set()
    opportunity_columns = {row[0] for row in target.execute("DESCRIBE opportunities").fetchall()} if "opportunities" in tables else set()

    seller_join = (
        "LEFT JOIN sellers s ON l.seller_id = s.id"
        if "sellers" in tables and "seller_id" in listing_columns
        else ""
    )
    search_join = (
        "LEFT JOIN searches se ON l.search_id = se.id"
        if "searches" in tables and "search_id" in listing_columns
        else ""
    )
    if not seller_join:
        seller_columns = set()
    if not search_join:
        search_columns = set()
    if "opportunities" in tables and "listing_id" in opportunity_columns:
        opportunity_join = """LEFT JOIN (
            SELECT listing_id, SUM(potential_profit) AS expected_profit,
                   AVG(confidence_score) AS opportunity_confidence
            FROM opportunities GROUP BY listing_id
        ) o ON l.id = o.listing_id"""
    else:
        opportunity_join = ""
    opportunity_projection = (
        "o.expected_profit, o.opportunity_confidence"
        if opportunity_join
        else "NULL::DOUBLE AS expected_profit, NULL::DOUBLE AS opportunity_confidence"
    )

    target.execute(
        f"""
        CREATE VIEW listing_facts AS
        SELECT
            {_column(listing_columns, "id")} AS listing_id,
            {_column(listing_columns, "title")} AS title,
            {_column(listing_columns, "price", type_name="DOUBLE")} AS asking_price,
            {_column(listing_columns, "created_at")} AS listed_at,
            {_column(listing_columns, "source")} AS source,
            {_column(listing_columns, "seller_id")} AS seller_id,
            {_column(seller_columns, "name", table="s")} AS seller_name,
            {_column(listing_columns, "search_id")} AS search_id,
            {_column(search_columns, "query", table="se")} AS search_query,
            {_column(listing_columns, "category")} AS category,
            {_column(listing_columns, "flip_score", type_name="DOUBLE")} AS flip_score,
            {_column(listing_columns, "keyword_score", type_name="DOUBLE")} AS keyword_score,
            {opportunity_projection}
        FROM listings l
        {seller_join}
        {search_join}
        {opportunity_join}
        """
    )


class Warehouse:
    """Owns a DuckDB snapshot and exposes read-only connections for reports."""

    def __init__(
        self,
        warehouse_path: str | Path | None = None,
        operational_path: str | Path | None = None,
    ) -> None:
        self.warehouse_path = Path(warehouse_path or DEFAULT_WAREHOUSE_PATH)
        self.operational_path = Path(operational_path or DEFAULT_OPERATIONAL_PATH)

    def sync(self) -> SyncMetrics:
        manager = SyncManager(self.operational_path, self.warehouse_path)
        with _INITIALIZATION_LOCK:
            with _operational_connection(self.operational_path) as source:
                tables = [t for t in _sqlite_tables(source) if t != "deleted_records"]
                metrics = manager.run_sync(tables)

                # Refresh views
                target = duckdb.connect(str(self.warehouse_path))
                try:
                    target.execute("DROP VIEW IF EXISTS listing_facts")
                    if "price_history" not in tables:
                        target.execute(
                            """
                            CREATE TABLE IF NOT EXISTS price_history (
                                listing_id VARCHAR,
                                price DOUBLE,
                                observed_at VARCHAR
                            )
                            """
                        )
                    _create_analytics_views(source, target)
                finally:
                    target.close()

            _INITIALIZED_WAREHOUSES.discard(self.warehouse_path.resolve())

        return metrics

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Return a read-only DuckDB connection for analytics queries."""
        if not self.warehouse_path.exists():
            raise FileNotFoundError(
                f"Analytics warehouse does not exist: {self.warehouse_path}. Run sync() first."
            )

        warehouse_path = self.warehouse_path.resolve()
        with _INITIALIZATION_LOCK:
            if warehouse_path not in _INITIALIZED_WAREHOUSES:
                with duckdb.connect(str(warehouse_path)) as writable:
                    _ensure_listing_facts_view(writable)
                _INITIALIZED_WAREHOUSES.add(warehouse_path)

            return duckdb.connect(str(warehouse_path), read_only=True)


def sync_operational_data(
    operational_path: str | Path | None = None,
    warehouse_path: str | Path | None = None,
) -> SyncMetrics:
    """Refresh the DuckDB warehouse from SQLite without mutating SQLite."""
    return Warehouse(
        warehouse_path=warehouse_path, operational_path=operational_path
    ).sync()
