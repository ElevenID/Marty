.PHONY: help install test lint package

help:
	@echo "install  Install retained infrastructure and source-test tooling"
	@echo "test     Run infrastructure and protocol source tests"
	@echo "lint     Run Ruff"
	@echo "package  Build the marty-common distribution"

install:
	python -m pip install -e "./packages/marty-common[test]" pytest==8.4.2 pytest-asyncio==1.2.0 ruff build

test:
	python -m pytest tests/unit packages/marty-common/tests -q

lint:
	python -m ruff check src packages/marty-common/marty_common scripts

package:
	python -m build packages/marty-common
