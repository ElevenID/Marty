# Multi-stage Dockerfile for passport-engine service
# Optimized with BuildKit cache mounts

# =============================================================================
# Builder Stage
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies for packages like pyscard
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpcsclite-dev \
    swig \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir uv

COPY Marty/pyproject.toml Marty/uv.lock Marty/README.md /app/

RUN uv pip install --system -e .

# =============================================================================
# Runtime Stage
# =============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install build dependencies for packages like pyscard
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpcsclite-dev \
    swig \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN mkdir -p /app/src/proto
COPY Marty/proto/ /app/proto/
COPY Marty/src/ /app/src/

RUN touch /app/proto/__init__.py && \
    touch /app/src/__init__.py && \
    touch /app/src/proto/__init__.py


RUN groupadd -r marty && useradd -r -g marty marty && \
    mkdir -p /app/data && chown -R marty:marty /app

USER marty

ENV SERVICE_NAME=passport-engine
ENV GRPC_PORT=8084
ENV PYTHONPATH=/app/src

CMD ["python", "-m", "src.apps.passport_engine"]
