.PHONY: help install test lint type-check format clean pre-commit

help:
	@echo "Available commands:"
	@echo "  install      Install dependencies with uv"
	@echo "  test         Run tests with pytest"
	@echo "  lint         Run linting with ruff"
	@echo "  type-check   Run type checking with mypy"
	@echo "  format       Format code with black"
	@echo "  clean        Remove cache files"
	@echo "  pre-commit   Install pre-commit hooks"

install:
	uv pip install -e ".[dev]"

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check src/ tests/

type-check:
	@echo "Running type checks..."
	@uv run mypy src/ --config-file=pyproject.toml || \
		(echo "Type errors found! These would have caught the DocType issue." && exit 1)

format:
	uv run black src/ tests/
	uv run ruff check --fix src/ tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +

pre-commit:
	uv pip install pre-commit
	pre-commit install
	@echo "Pre-commit hooks installed! They will run on every commit."