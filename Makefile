.PHONY: help install test lint package

help:
	@echo "install  Install this repository from released dependencies"
	@echo "test     Run repository tests"
	@echo "lint     Run Ruff"
	@echo "package  Build the Python package"

install:
	python -m pip install -e . pytest ruff build

test:
	python -m pytest tests/unit -q

lint:
	python -m ruff check src tests

package:
	python -m build
