from typing import Any, Optional, Protocol

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import DATABASE_URL
from database.models import DeletedRecord, Listing, Queue  # noqa: F401


class DatabaseInitializer(Protocol):
    def initialize(self, engine: Engine) -> None: ...


class SQLiteInitializer:
    def initialize(self, engine: Engine) -> None:
        """Keep SQLite schema details and delete tracking triggers current."""
        self._migrate_listing_identity(engine)
        tables = [
            "sellers",
            "searches",
            "listings",
            "images",
            "price_history",
            "opportunities",
            "queues",
            "purchases",
        ]
        with engine.connect() as conn:
            for table in tables:
                trigger_name = f"after_delete_{table}"
                conn.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
                conn.execute(
                    text(f"""
                    CREATE TRIGGER {trigger_name}
                    AFTER DELETE ON {table}
                    BEGIN
                        INSERT INTO deleted_records (table_name, record_id, deleted_at)
                        VALUES ('{table}', OLD.id, CURRENT_TIMESTAMP);
                    END;
                    """)
                )
            conn.commit()

    @staticmethod
    def _migrate_listing_identity(engine: Engine) -> None:
        inspector = inspect(engine)
        if "listings" not in inspector.get_table_names():
            return

        listing_columns = {column["name"] for column in inspector.get_columns("listings")}
        if "created_at" not in listing_columns or "external_id" not in listing_columns:
            with engine.begin() as conn:
                conn.exec_driver_sql("ALTER TABLE listings RENAME TO listings_legacy")
                SQLiteInitializer._create_listings_table(conn)
                conn.exec_driver_sql(
                    """
                    INSERT INTO listings
                        (id, title, description, price, source, external_id, url,
                         status, created_at, updated_at, version)
                    SELECT lower(hex(randomblob(16))), title, description, price,
                           COALESCE(source, 'legacy'),
                           COALESCE(url, CAST(id AS TEXT)), url,
                           UPPER(COALESCE(status, 'new')),
                           COALESCE(date_found, CURRENT_TIMESTAMP),
                           COALESCE(date_found, CURRENT_TIMESTAMP), 1
                    FROM listings_legacy
                    """
                )
                SQLiteInitializer._create_listing_indexes(conn)
            return

        unique_constraints = inspector.get_unique_constraints("listings")
        has_source_scoped_identity = any(
            constraint.get("column_names") == ["source", "external_id"]
            for constraint in unique_constraints
        )
        if has_source_scoped_identity:
            return

        with engine.begin() as conn:
            conn.exec_driver_sql(
                """
                CREATE TABLE listings_source_scoped (
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
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER NOT NULL DEFAULT 1,
                    CONSTRAINT uq_listings_source_external_id
                        UNIQUE (source, external_id),
                    FOREIGN KEY(seller_id) REFERENCES sellers (id),
                    FOREIGN KEY(search_id) REFERENCES searches (id)
                )
                """
            )
            conn.exec_driver_sql(
                """
                INSERT INTO listings_source_scoped
                    (id, title, description, price, source, external_id, url,
                     status, seller_id, search_id, created_at, updated_at, version)
                WITH ranked AS (
                    SELECT id, title, description, price, source, external_id, url,
                           status, seller_id, search_id, created_at, updated_at,
                           version,
                           ROW_NUMBER() OVER (
                               PARTITION BY source,
                                   CASE
                                       WHEN external_id IS NULL THEN id
                                       ELSE external_id
                                   END
                               ORDER BY created_at, id
                           ) AS row_number
                    FROM listings
                )
                  SELECT id, title, description, price, source, external_id, url,
                      UPPER(status), seller_id, search_id, created_at, updated_at, version
                FROM ranked
                WHERE row_number = 1
                """
            )
            conn.exec_driver_sql("DROP TABLE listings")
            conn.exec_driver_sql(
                "ALTER TABLE listings_source_scoped RENAME TO listings"
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_listings_title ON listings (title)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_listings_source ON listings (source)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_listings_external_id ON listings (external_id)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_listings_status ON listings (status)"
            )

    @staticmethod
    def _create_listings_table(conn: Any) -> None:
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
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                version INTEGER NOT NULL DEFAULT 1,
                CONSTRAINT uq_listings_source_external_id
                    UNIQUE (source, external_id),
                FOREIGN KEY(seller_id) REFERENCES sellers (id),
                FOREIGN KEY(search_id) REFERENCES searches (id)
            )
            """
        )

    @staticmethod
    def _create_listing_indexes(conn: Any) -> None:
        for column in ("title", "source", "external_id", "status"):
            conn.exec_driver_sql(
                f"CREATE INDEX ix_listings_{column} ON listings ({column})"
            )


class UnsupportedDatabaseError(RuntimeError):
    """Raised when a configured database backend is not supported yet."""


def get_engine(database_url: Optional[str] = None) -> Engine:
    url = database_url or DATABASE_URL
    
    if not url.startswith(("sqlite", "postgresql", "mysql")):
        url = f"sqlite:///{url}"
    
    # Common engine configuration
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        
    return create_engine(url, connect_args=connect_args)


def get_session(
    database_url: Optional[str] = None, *, expire_on_commit: bool = False
) -> Session:
    return Session(get_engine(database_url), expire_on_commit=expire_on_commit)


def connect(database_url: Optional[str] = None) -> Session:
    return get_session(database_url)


def initialize_database(database_url: Optional[str] = None) -> Engine:
    url = database_url or DATABASE_URL

    if url.startswith("postgresql"):
        raise UnsupportedDatabaseError(
            "PostgreSQL is not supported yet. Use SQLite, or follow "
            "MIGRATION_STRATEGY.md before configuring a PostgreSQL database."
        )

    engine = get_engine(url)
    
    # Create tables
    SQLModel.metadata.create_all(engine)
    
    # Dialect-specific initialization
    if url.startswith("sqlite"):
        SQLiteInitializer().initialize(engine)
        
    return engine


def initialize() -> Engine:
    return initialize_database()


def add_listing(listing: dict) -> None:
    with connect() as session:
        entry = Listing(
            title=listing["title"],
            description=listing.get("description"),
            price=float(listing["price"]),
            source=listing["source"],
            external_id=listing.get("url"),
            url=listing.get("url"),
        )
        session.add(entry)
        session.commit()
