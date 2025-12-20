# syntax=docker/dockerfile:1
# Multi-stage Dockerfile for csca-service
# Optimized with BuildKit cache mounts

# =============================================================================
# Builder Stage
# =============================================================================
FROM python:3.10-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir uv

COPY ../../pyproject.toml ../../uv.lock /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv pip install --system -e .

# =============================================================================
# Runtime Stage
# =============================================================================
FROM python:3.10-slim AS runtime

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN mkdir -p /app/src/proto
COPY ../../proto/ /app/proto/
COPY ../../src/ /app/src/

RUN touch /app/proto/__init__.py && \
    touch /app/src/__init__.py && \
    touch /app/src/proto/__init__.py

RUN cd /app && python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./src/proto \
    --grpc_python_out=./src/proto \
    ./proto/*.proto

RUN groupadd -r marty && useradd -r -g marty marty && \
    mkdir -p /app/data && chown -R marty:marty /app

USER marty

ENV SERVICE_NAME=csca-service
ENV GRPC_PORT=8081
ENV PYTHONPATH=/app/src

CMD ["python", "-m", "src.apps.csca_service"]
