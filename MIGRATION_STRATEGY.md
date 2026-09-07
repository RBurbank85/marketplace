# Migration Strategy: SQLite to PostgreSQL

This document outlines the strategy for migrating the MAIE operational database from SQLite to PostgreSQL.

## 1. Abstraction Layer (SQLite only)
The codebase has been refactored to support multiple database backends:
- **`database_url` in Settings**: Retains the planned PostgreSQL connection string shape (`postgresql://user:password@host:port/dbname`), but PostgreSQL is not a supported deployment target yet. Application initialization rejects it explicitly.
- **Dialect-Agnostic Repositories**: `DatabaseRepository` handles basic CRUD operations without dialect-specific SQL.
- **Strategy Pattern for Initialization**: SQLite-specific triggers are isolated in `SQLiteInitializer`. PostgreSQL trigger initialization is not implemented, so it is rejected rather than reported as initialized.
- **Optimistic Locking**: Added `version` column and `version_id_col` mapper arguments to support concurrent workers and prevent lost updates.

## 2. Migration Tooling
We recommend using **Alembic** for managing schema migrations.
- **Setup**: `uv add alembic`
- **Initialization**: `alembic init migrations`
- **Configuration**: Update `alembic.ini` and `env.py` to use the `SQLModel` metadata and the `DATABASE_URL` from the application settings.

## 3. Data Migration Steps
When moving existing data from `listings.db` to a PostgreSQL instance:
1. **Schema Creation**: Use Alembic to create the schema in the target PostgreSQL database.
2. **Data Export**: Export SQLite data to CSV or JSON, or use a tool like `pgloader`.
3. **Data Type Mapping**: 
   - SQLite `TEXT` -> PostgreSQL `TEXT` or `VARCHAR`.
   - SQLite `BLOB` -> PostgreSQL `BYTEA`.
   - SQLite `UUID` (stored as string) -> PostgreSQL `UUID` (native).
4. **Trigger Implementation**: Implement the PostgreSQL version of the `after_delete` triggers using PL/pgSQL functions.

## 4. Concurrent Workers Support
PostgreSQL's MVCC and the newly added optimistic locking support high concurrency.
- **Connection Pooling**: SQLAlchemy's `QueuePool` (default for PostgreSQL) should be tuned based on the number of workers.
- **Transaction Isolation**: Default `READ COMMITTED` is usually sufficient, but can be adjusted if needed.

## 5. Deployment status
PostgreSQL is deferred. Do not set `DATABASE_URL` to a PostgreSQL URL for an application deployment; `initialize_database()` raises `UnsupportedDatabaseError` with an actionable message. The migration steps above are planning guidance only until a PostgreSQL driver, schema migration workflow, and dialect-correct deleted-record triggers are added.
