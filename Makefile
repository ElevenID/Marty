.PHONY: help install test lint package image up down clean

VERSION ?= 1.0.0
MARTY_MSF_VERSION ?= 1.0.0

help:
	@echo "install  Install this repository from released dependencies"
	@echo "test     Run repository tests"
	@echo "lint     Run Ruff"
	@echo "package  Build the Python package"
	@echo "image    Build the Marty image from this repository only"
	@echo "up       Run MARTY_IMAGE (must be pinned by digest)"

install:
	python -m pip install -e . pytest ruff build

test:
	python -m pytest tests/unit -q

lint:
	python -m ruff check src tests

package:
	python -m build

image:
	docker build --file docker/mmf-plugin.Dockerfile \
		--build-arg VERSION=$(VERSION) \
		--build-arg VCS_REF=$$(git rev-parse HEAD) \
		--build-arg MARTY_MSF_VERSION=$(MARTY_MSF_VERSION) \
		--tag marty:$(VERSION) .

up:
	@echo "$(MARTY_IMAGE)" | grep -Eq '^ghcr\.io/elevenid/marty@sha256:[0-9a-f]{64}$$'
	docker compose up -d --wait

down:
	docker compose down

clean:
	docker compose down -v
