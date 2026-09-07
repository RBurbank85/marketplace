from typing import Optional, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import DATABASE_URL
from database.models import DeletedRecord, Listing, Queue  # noqa: F401


class DatabaseInitializer(Protocol):
    def initialize(self, engine: Engine) -> None: ...


class SQLiteInitializer:
    def initialize(self, engine: Engine) -> None:
        """Set up SQLite triggers to track deleted records."""
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
