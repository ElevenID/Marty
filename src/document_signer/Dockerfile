# syntax=docker/dockerfile:1
# Multi-stage Dockerfile for document-signer service
# Optimized with BuildKit cache mounts

# =============================================================================
# Builder Stage
# =============================================================================
FROM python:3.10-slim AS builder

WORKDIR /app

# Install UV and build dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir uv

COPY ../../pyproject.toml ../../uv.lock /app/

# Install dependencies with BuildKit cache
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv pip install --system -e .

# =============================================================================
# Runtime Stage
# =============================================================================
FROM python:3.10-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create the proto directory structure
RUN mkdir -p /app/src/proto

# Copy the proto files
COPY ../../proto/ /app/proto/

# Copy the source code
COPY ../../src/ /app/src/

# Make directories Python packages
RUN touch /app/proto/__init__.py
RUN touch /app/src/__init__.py
RUN touch /app/src/proto/__init__.py

# Generate Python code from proto files directly into src/proto/
RUN cd /app && python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./src/proto \
    --grpc_python_out=./src/proto \
    ./proto/*.proto

# Create non-root user
RUN groupadd -r marty && useradd -r -g marty marty

# Create data directories with proper permissions
RUN mkdir -p /app/data && chown -R marty:marty /app

USER marty

# Command to run when container starts
ENV SERVICE_NAME=document-signer
ENV GRPC_PORT=8082
ENV PYTHONPATH=/app/src

CMD ["python", "-m", "src.apps.document_signer"]
