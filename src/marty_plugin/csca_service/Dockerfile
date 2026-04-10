# Multi-stage Dockerfile for csca-service
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

# Build context is parent directory containing both Marty and marty-microservices-framework
# Copy only necessary files to keep context small
COPY Marty/pyproject.toml Marty/uv.lock Marty/README.md /app/
COPY Marty/rust /app/rust
COPY Marty/src /app/src
COPY Marty/proto /app/proto
COPY marty-microservices-framework /marty-microservices-framework

RUN uv pip install --system -e .

# =============================================================================
# Runtime Stage
# =============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN mkdir -p /app/src/proto
COPY Marty/proto/ /app/proto/
COPY Marty/src/ /app/src/

RUN touch /app/proto/__init__.py && \
    touch /app/src/__init__.py && \
    touch /app/src/proto/__init__.py


# License entrypoint
COPY Marty/docker/license-entrypoint.sh /usr/local/bin/license-entrypoint.sh
RUN chmod +x /usr/local/bin/license-entrypoint.sh

# Create license key mount point
RUN mkdir -p /etc/marty

RUN groupadd -r marty && useradd -r -g marty marty && \
    mkdir -p /app/data && chown -R marty:marty /app /etc/marty

USER marty

ENV SERVICE_NAME=csca-service
ENV GRPC_PORT=8081
ENV PYTHONPATH=/app/src
ENV MARTY_PRODUCT_ID=csca-service

ENTRYPOINT ["/usr/local/bin/license-entrypoint.sh"]
CMD ["python", "-m", "src.apps.csca_service"]
