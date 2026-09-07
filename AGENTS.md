# Repository Guidelines

MAIE (Marketplace Arbitrage Intelligence Engine) is a modular Python system for marketplace monitoring and arbitrage analysis. It uses a plugin-based architecture to allow easy extension of collectors, categories, and analysis logic.

## Project Structure & Module Organization

The project follows a layered architecture with clear boundaries between data collection, analysis, and persistence:

- **`./collectors/`**: Marketplace-specific adapters implementing the `BaseCollector` interface. They handle searching, fetching, and normalizing data. Parsers are located in `./collectors/parsers/`.
- **`./analysis/`**: Scoring (FlipScore), classification, and enrichment logic. Isolated from data collection.
- **`./categories/`**: Domain-specific knowledge plugins (e.g., `electronics.py`, `tools.py`) that provide search keywords and category-specific margins.
- **`./core/`**: Shared domain logic, plugin registry, and the runtime scheduler.
- **`./database/`**: Persistence layer using SQLModel (operational SQLite) and DuckDB (analytics).
- **`./analytics/`**: reporting queries and DuckDB warehouse logic.
- **`./app/`**: CLI entry point and application wiring using Typer.

## Build, Test, and Development Commands

The project uses `uv` for dependency management.

- **Install dependencies**: `uv pip install -e ".[dev]"`
- **Run tests**: `uv run pytest`
- **Lint code**: `uv run ruff check .`
- **Format code**: `uv run ruff format .`
- **Run CLI**: `uv run maie --help`

These direct `uv` commands work on Windows PowerShell and POSIX shells. The
Makefile remains available as an optional wrapper where GNU make is installed.

## Coding Style & Naming Conventions

- **Tooling**: Enforced via `ruff` for linting and formatting.
- **Typing**: Strong emphasis on type hints and Pydantic/SQLModel schemas for data validation.
- **Concurrency**: Business logic should remain framework-agnostic where possible, with concurrency handled by the `core.scheduler`.
- **Naming**: Follow standard Python (PEP 8) conventions. Modules should be small and focused.

## Testing Guidelines

- **Framework**: `pytest` is used for all tests.
- **Location**: All tests are located in the `./tests/` directory.
- **Execution**: Run the full suite with `make test`. To run a specific test file: `uv run pytest tests/test_filename.py`.
- **Conventions**: Each major module should have a corresponding test file in `./tests/`.

## Commit & Pull Request Guidelines

- **Commit Messages**: Use concise, descriptive messages (e.g., "built the foundation", "Initial marketplace AI engine").
- **Workflow**: Ensure `make lint` and `make test` pass before submitting any changes.

## Parsing Architecture

The project uses a resilient parsing architecture to handle marketplace search results:

- **Interface**: Defined in `./core/parsing.py` as `BaseParser` (a Protocol).
- **Implementation**: Each marketplace has its own parser in `./collectors/parsers/` (e.g., `./collectors/parsers/craigslist.py`).
- **Resilience**: Parsers prefer `selectolax` for performance but fall back to `BeautifulSoup` if not available.
- **Registry**: Parsers are registered in the `ParserRegistry` in `./core/parsing.py` for dynamic retrieval.
- **CSS Selectors**: Parsers use CSS selectors instead of manual state machines for better maintainability.
- **Testing**: Parsers are tested using HTML fixtures in `./tests/fixtures/` to avoid live scraping during tests.
