.PHONY: install check corpus evaluate demo test lint

install:
	python -m venv .venv && .venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check src tests

check:
	.venv/bin/mandate check

corpus:
	.venv/bin/mandate corpus build --seed 20260901

evaluate:
	.venv/bin/mandate evaluate --seed 20260901 --arms baseline,mandate

demo:
	.venv/bin/mandate demo --seed 20260901
