from __future__ import annotations

import pytest
from sqlalchemy.orm.exc import StaleDataError
from database.database import (
    SQLiteInitializer,
    UnsupportedDatabaseError,
    initialize_database,
)
from database.models import Seller
from database.repositories import ListingRepository, SellerRepository

def test_optimistic_locking(tmp_path):
    """Verify that optimistic locking works using the version column."""
    db_url = f"sqlite:///{tmp_path / 'test_locking.db'}"
    initialize_database(db_url)
    
    repo = SellerRepository(database_url=db_url)
    seller = repo.create(Seller(name="Original Name"))
    
    # Fetch two instances of the same record
    s1 = repo.get_by_id(seller.id)
    s2 = repo.get_by_id(seller.id)
    
    assert s1.version == 1
    assert s2.version == 1
    
    # Update the first instance
    repo.update(s1.id, {"name": "First Update"})
    
    # Verify version incremented
    updated_s1 = repo.get_by_id(seller.id)
    assert updated_s1.version == 2
    
    # Attempt to update the second (stale) instance
    with pytest.raises(StaleDataError):
        # We need to use the stale object directly in a way that triggers the check.
        # The repository's update method currently fetches the latest instance by ID.
        # To test optimistic locking, we need to try to save an object with an old version.
        with repo.session() as session:
            s2.name = "Stale Update"
            session.add(s2)
            # This should raise StaleDataError on commit/flush because version is still 1
            session.flush()

def test_dialect_detection(tmp_path):
    """Verify SQLite initialization and explicit PostgreSQL support status."""
    sqlite_url = f"sqlite:///{tmp_path / 'test.db'}"
    postgres_url = "postgresql://user:pass@localhost/db"
    
    # We can't easily test initialize_database with a fake postgres URL without a driver,
    # but we can test the logic if we mock the engine creation or just check the URL.
    from database.database import get_engine
    
    engine_sqlite = get_engine(sqlite_url)
    assert engine_sqlite.dialect.name == "sqlite"
    
    from unittest.mock import MagicMock, patch
    
    with patch("database.database.create_engine") as mock_create_engine:
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        with patch.object(SQLiteInitializer, "initialize") as mock_sqlite_init:
            initialize_database(sqlite_url)
            mock_sqlite_init.assert_called_once()
            
        with pytest.raises(UnsupportedDatabaseError, match="PostgreSQL is not supported"):
            initialize_database(postgres_url)

        mock_create_engine.assert_called_once_with(
            sqlite_url, connect_args={"check_same_thread": False}
        )


def test_listing_identity_migration_adds_source_scope_and_keeps_first_duplicate(
    tmp_path,
):
    database_url = str(tmp_path / "legacy-listings.db")
    engine = initialize_database(database_url)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE listings")
        conn.exec_driver_sql(
            """
            CREATE TABLE listings (
                id CHAR(32) NOT NULL PRIMARY KEY,
                title VARCHAR NOT NULL,
                description VARCHAR,
                price FLOAT NOT NULL,
                source VARCHAR NOT NULL,
                external_id VARCHAR,
                url VARCHAR,
                status VARCHAR NOT NULL,
                seller_id CHAR(32),
                search_id CHAR(32),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO listings
                (id, title, price, source, external_id, url, status,
                 created_at, updated_at)
            VALUES
                ('00000000000000000000000000000001', 'First', 10, 'craigslist',
                 'shared', 'https://example.test/1', 'new',
                 '2026-01-01', '2026-01-01'),
                ('00000000000000000000000000000002', 'Later', 20, 'craigslist',
                 'shared', 'https://example.test/2', 'new',
                 '2026-01-02', '2026-01-02'),
                ('00000000000000000000000000000003', 'Facebook', 30, 'facebook',
                 'shared', 'https://example.test/3', 'new',
                 '2026-01-01', '2026-01-01')
            """
        )

    SQLiteInitializer().initialize(engine)

    listings = ListingRepository(database_url).list()
    assert {(item.source, item.external_id) for item in listings} == {
        ("craigslist", "shared"),
        ("facebook", "shared"),
    }
    assert ListingRepository(database_url).get_by_external_id(
        "shared", "craigslist"
    ).title == "First"
