"""Incremental synchronization for the DuckDB analytics warehouse.

This module provides components for tracking changes in the operational SQLite
database and applying them efficiently to the DuckDB warehouse using
batch processing and timestamp-based change tracking.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb


@dataclass
class TableMetrics:
    """Metrics for an individual table sync operation."""

    inserted_or_updated: int = 0
    deleted: int = 0
    errors: int = 0


@dataclass
class SyncMetrics:
    """Tracking metrics for a synchronization session."""

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    tables_synced: Dict[str, TableMetrics] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if not self.end_time:
            return (datetime.now(timezone.utc) - self.start_time).total_seconds()
        return (self.end_time - self.start_time).total_seconds()

    @property
    def tables(self) -> Dict[str, int]:
        """Return copied row counts for the snapshot result API."""
        return {
            table_name: table_metrics.inserted_or_updated
            for table_name, table_metrics in self.tables_synced.items()
        }


class BatchProcessor:
    """Handles efficient batch updates to DuckDB."""

    def __init__(self, connection: duckdb.DuckDBPyConnection, batch_size: int = 10000):
        self.connection = connection
        self.batch_size = batch_size

    def upsert_batch(self, table_name: str, columns: List[str], records: List[Tuple]):
        """Perform an UPSERT-like operation in DuckDB by deleting existing IDs and inserting."""
        if not records:
            return

        id_index = columns.index("id")
        ids = [str(r[id_index]) for r in records]

        # Process in sub-batches to avoid overly long query strings if needed,
        # though DuckDB handles large queries well.
        ids_str = ", ".join(f"'{i}'" for i in ids)
        self.connection.execute(f"DELETE FROM {table_name} WHERE id IN ({ids_str})")

        placeholders = ", ".join(["?"] * len(columns))
        self.connection.executemany(
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
            records,
        )

    def delete_batch(self, table_name: str, ids: List[str]):
        """Perform a batch delete in DuckDB."""
        if not ids:
            return
        ids_str = ", ".join(f"'{str(i)}'" for i in ids)
        self.connection.execute(f"DELETE FROM {table_name} WHERE id IN ({ids_str})")


class ChangeTracker:
    """Identifies new, updated, and deleted records in SQLite."""

    def __init__(self, sqlite_conn: sqlite3.Connection):
        self.sqlite_conn = sqlite_conn

    def get_column_info(self, table_name: str) -> List[Tuple[str, str]]:
        """Return list of (column_name, data_type)."""
        cursor = self.sqlite_conn.execute(f"PRAGMA table_info('{table_name}')")
        return [(row[1], row[2]) for row in cursor.fetchall()]

    def get_changes(
        self, table_name: str, last_sync: datetime
    ) -> Tuple[List[Tuple], List[str], List[str]]:
        """Return (updated_records, column_names, deleted_ids)."""
        columns_info = self.get_column_info(table_name)
        columns = [info[0] for info in columns_info]

        if "updated_at" not in columns:
            records = self.sqlite_conn.execute(
                f"SELECT * FROM {table_name}"
            ).fetchall()
            return records, columns, []

        # SQLite often uses space instead of 'T' for ISO timestamps.
        # Normalize last_sync to match SQLite's default format if needed,
        # or use datetime() function for robust comparison.
        last_sync_str = last_sync.strftime("%Y-%m-%d %H:%M:%S.%f")

        # Get new/updated records
        query = f"SELECT * FROM {table_name} WHERE updated_at > ?"
        records = self.sqlite_conn.execute(query, (last_sync_str,)).fetchall()

        # Get deleted records from our audit table
        del_query = "SELECT record_id FROM deleted_records WHERE table_name = ? AND deleted_at > ?"
        has_deleted_records = self.sqlite_conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'deleted_records'"
        ).fetchone()
        deleted_ids = (
            [
                row[0]
                for row in self.sqlite_conn.execute(
                    del_query, (table_name, last_sync_str)
                ).fetchall()
            ]
            if has_deleted_records
            else []
        )

        return records, columns, deleted_ids


class SyncManager:
    """Orchestrates the incremental synchronization process."""

    def __init__(
        self, operational_path: Path, warehouse_path: Path, batch_size: int = 10000
    ):
        self.operational_path = operational_path
        self.warehouse_path = warehouse_path
        self.batch_size = batch_size

    def _get_last_sync(
        self, connection: duckdb.DuckDBPyConnection, table_name: str
    ) -> datetime:
        """Get last sync time for a table from DuckDB metadata."""
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_metadata (
                table_name VARCHAR PRIMARY KEY,
                last_sync_at TIMESTAMP
            )
        """
        )
        res = connection.execute(
            "SELECT last_sync_at FROM sync_metadata WHERE table_name = ?", (table_name,)
        ).fetchone()

        if res and res[0]:
            # DuckDB TIMESTAMP might need conversion or already be datetime
            ts = res[0]
            if isinstance(ts, datetime):
                return ts.replace(tzinfo=timezone.utc)
            return datetime.fromisoformat(str(ts)).replace(tzinfo=timezone.utc)
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    def _set_last_sync(
        self,
        connection: duckdb.DuckDBPyConnection,
        table_name: str,
        sync_time: datetime,
    ):
        connection.execute(
            """
            INSERT INTO sync_metadata (table_name, last_sync_at) VALUES (?, ?)
            ON CONFLICT (table_name) DO UPDATE SET last_sync_at = excluded.last_sync_at
            """,
            (table_name, sync_time),
        )

    def _ensure_table_exists(
        self,
        table_name: str,
        tracker: ChangeTracker,
        duck_conn: duckdb.DuckDBPyConnection,
    ):
        """Ensure the table exists in DuckDB, creating it if necessary."""
        exists = duck_conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            (table_name,),
        ).fetchone()[0]

        if not exists:
            columns_info = tracker.get_column_info(table_name)

            def map_type(sqlite_type: str | None) -> str:
                declared = (sqlite_type or "").upper()
                if "INT" in declared:
                    return "BIGINT"
                if any(
                    token in declared
                    for token in ("REAL", "FLOA", "DOUB", "NUMERIC", "DECIMAL")
                ):
                    return "DOUBLE"
                if "BOOL" in declared:
                    return "BOOLEAN"
                if "BLOB" in declared:
                    return "BLOB"
                return "VARCHAR"

            definitions = ", ".join(
                f'"{info[0]}" {map_type(info[1])}' for info in columns_info
            )
            duck_conn.execute(f"CREATE TABLE {table_name} ({definitions})")

    def sync_table(
        self,
        table_name: str,
        sqlite_conn: sqlite3.Connection,
        duck_conn: duckdb.DuckDBPyConnection,
        metrics: SyncMetrics,
    ):
        tracker = ChangeTracker(sqlite_conn)
        processor = BatchProcessor(duck_conn, self.batch_size)

        self._ensure_table_exists(table_name, tracker, duck_conn)

        last_sync = self._get_last_sync(duck_conn, table_name)
        # Use a stable sync time for this run.
        # Capture it BEFORE fetching to avoid missing records updated during sync.
        new_sync_time = datetime.now(timezone.utc)

        records, columns, deleted_ids = tracker.get_changes(table_name, last_sync)

        table_metrics = TableMetrics()

        # Process updates/inserts in batches
        for i in range(0, len(records), self.batch_size):
            batch = records[i : i + self.batch_size]
            processor.upsert_batch(table_name, columns, batch)
            table_metrics.inserted_or_updated += len(batch)

        # Process deletes in batches
        for i in range(0, len(deleted_ids), self.batch_size):
            batch = deleted_ids[i : i + self.batch_size]
            processor.delete_batch(table_name, batch)
            table_metrics.deleted += len(batch)

        self._set_last_sync(duck_conn, table_name, new_sync_time)
        metrics.tables_synced[table_name] = table_metrics

    def run_sync(self, tables: List[str]) -> SyncMetrics:
        """Run incremental sync for the specified tables."""
        metrics = SyncMetrics()

        # Ensure directory exists
        self.warehouse_path.parent.mkdir(parents=True, exist_ok=True)

        # Mode=ro ensures we don't accidentally write to SQLite
        sqlite_uri = f"{self.operational_path.resolve().as_uri()}?mode=ro"

        with sqlite3.connect(sqlite_uri, uri=True) as sqlite_conn:
            duck_conn = duckdb.connect(str(self.warehouse_path))
            try:
                duck_conn.execute("BEGIN TRANSACTION")
                for table in tables:
                    self.sync_table(table, sqlite_conn, duck_conn, metrics)
                duck_conn.execute("COMMIT")
            except Exception:
                duck_conn.execute("ROLLBACK")
                raise
            finally:
                metrics.end_time = datetime.now(timezone.utc)
                duck_conn.close()

        return metrics
