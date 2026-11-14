.PHONY: all run check lint test format record unicode clean

all: check

run:
	uv run python -m side_vim

check: lint test

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest

format:
	uv run ruff format .

# runs real vim on tests/cases and writes the expected results back
record:
	uv run python scripts/record_vim.py

# dumps vim's character classes and widths into side_vim/_unicode_data.py
unicode:
	uv run python scripts/unicode_tables.py

clean:
	rm -rf build dist
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +
