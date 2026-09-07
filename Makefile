.PHONY: install test coverage quality lint format

install:
	uv pip install -e ".[dev]"

test:
	uv run pytest

coverage:
	uv run pytest --cov=. --cov-report=term-missing

quality:
	uv run ruff check .
	uv run pytest --cov=. --cov-report=term-missing

lint:
	uv run ruff check .

format:
	uv run ruff format .
